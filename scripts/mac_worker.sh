#!/usr/bin/env bash
# mac_worker.sh — Mac 本地 YouTube 处理守护进程
# 每30秒轮询云端队列，有任务就本地处理，结果回传云端
#
# 启动方式（后台常驻）：
#   nohup bash ~/Auto-Grasp-Pipeline/scripts/mac_worker.sh >> ~/mac_worker.log 2>&1 &
#
# 停止：
#   kill $(cat /tmp/mac_worker.pid)

set -euo pipefail

QUEUE_URL="${N8N_CLOUD_URL:-http://54.169.36.2:5678}/webhook/yt-queue"
DONE_URL="${N8N_CLOUD_URL:-http://54.169.36.2:5678}/webhook/yt-queue/done"
PYTHON="${VENV_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3}"
WHISPER_MODEL="${WHISPER_MODEL:-small}"
POLL_INTERVAL=30

echo $$ > /tmp/mac_worker.pid
echo "[mac_worker] 启动 PID=$$  $(date)"
echo "[mac_worker] 轮询地址: $QUEUE_URL"

while true; do
  # ── 1. 拉取待处理任务 ─────────────────────────────────────────────────────
  resp=$(curl -s --max-time 10 "$QUEUE_URL" 2>/dev/null || echo '{"jobs":[]}')
  jobs=$("$PYTHON" -c "
import sys, json
d = json.loads('''$resp''')
jobs = d.get('jobs', [])
print(json.dumps(jobs))
" 2>/dev/null || echo '[]')

  count=$("$PYTHON" -c "import json,sys; print(len(json.loads('$jobs')))" 2>/dev/null || echo 0)

  if [[ "$count" -gt 0 ]]; then
    echo "[mac_worker] $(date '+%H:%M:%S') 收到 $count 个任务"

    # ── 2. 逐个处理 ───────────────────────────────────────────────────────────
    "$PYTHON" - "$jobs" "$DONE_URL" "$PYTHON" "$WHISPER_MODEL" <<'PYEOF'
import sys, json, subprocess, tempfile, os
from pathlib import Path

jobs      = json.loads(sys.argv[1])
done_url  = sys.argv[2]
python    = sys.argv[3]
model     = sys.argv[4]

import urllib.request, urllib.error

def post_json(url, payload):
    data = json.dumps(payload, ensure_ascii=False).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()
    except Exception as e:
        return str(e)

for job in jobs:
    job_id = job.get("job_id", "")
    url    = job.get("url", "")
    run_id = job.get("run_id", "")
    print(f"  处理: {url[:60]}  job_id={job_id}")

    with tempfile.TemporaryDirectory() as td:
        # 1. yt-dlp 下载音频（优先 chrome cookies）
        audio_out = f"{td}/audio.%(ext)s"
        dl_cmds = [
            ["yt-dlp", "-f", "bestaudio", "--no-playlist",
             "--cookies-from-browser", "chrome",
             "-o", audio_out, url],
            ["yt-dlp", "-f", "bestaudio", "--no-playlist",
             "--cookies-from-browser", "safari",
             "-o", audio_out, url],
            ["yt-dlp", "-f", "bestaudio", "--no-playlist",
             "-o", audio_out, url],
        ]
        dl_ok = False
        for cmd in dl_cmds:
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode == 0:
                dl_ok = True
                break

        if not dl_ok:
            print(f"  ✗ 下载失败，跳过 {job_id}")
            post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                  "ok": False, "error": "download_failed"})
            continue

        audio_files = list(Path(td).glob("audio.*"))
        if not audio_files:
            post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                  "ok": False, "error": "no_audio_file"})
            continue

        # 2. 转换为 16kHz WAV
        wav = f"{td}/audio.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_files[0]), "-vn", "-ac", "1", "-ar", "16000", wav],
            capture_output=True
        )

        # 3. Whisper 转录
        code = f"""
from faster_whisper import WhisperModel
import json
model = WhisperModel({model!r}, device="cpu", compute_type="int8")
segs, info = model.transcribe({wav!r}, vad_filter=True)
text = " ".join(s.text.strip() for s in segs)
print(json.dumps({{"ok": True, "text": text, "lang": info.language}}))
"""
        wp = subprocess.run([python, "-c", code], capture_output=True, text=True)
        try:
            wout = json.loads(wp.stdout.strip().splitlines()[-1])
        except Exception:
            post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                  "ok": False, "error": "whisper_failed"})
            continue

        transcript = wout.get("text", "")
        chars = len(transcript)
        print(f"  ✓ 转录完成 {chars} 字符  lang={wout.get('lang')}")

        # 4. 回传云端
        result = post_json(done_url, {
            "job_id": job_id,
            "run_id": run_id,
            "url": url,
            "ok": True,
            "raw_text": transcript,
            "chars": chars,
            "language": wout.get("lang", "zh")
        })
        print(f"  → 回传结果: {result[:80]}")

print("  本轮处理完毕")
PYEOF

  else
    # 无任务，静默等待
    :
  fi

  sleep "$POLL_INTERVAL"
done
