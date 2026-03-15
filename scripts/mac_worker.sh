#!/usr/bin/env bash
# mac_worker.sh — Mac 本地 YouTube 处理守护进程
# 每30秒轮询云端队列，有任务就本地处理，结果回传云端
#
# 启动方式（后台常驻）：
#   nohup bash ~/Auto-Grasp-Pipeline/scripts/mac_worker.sh >> ~/mac_worker.log 2>&1 &
#
# 停止：
#   kill $(cat /tmp/mac_worker.pid)

QUEUE_URL="${QUEUE_GET_URL:-http://54.169.36.2:8080/api/yt-queue?token=oc_ingest_mOmwEGAyQTlxMKvw1VemodYo}"
DONE_URL="${DONE_POST_URL:-http://54.169.36.2:8080/api/yt-queue/done?token=oc_ingest_mOmwEGAyQTlxMKvw1VemodYo}"
PYTHON="${VENV_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3}"
WHISPER_MODEL="${WHISPER_MODEL:-small}"
POLL_INTERVAL=30
TMP_RESP=/tmp/mac_worker_resp.json
# 确保 subprocess 能找到 yt-dlp / ffmpeg / deno
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

echo $$ > /tmp/mac_worker.pid
echo "[mac_worker] 启动 PID=$$  $(date)"
echo "[mac_worker] 轮询地址: $QUEUE_URL"

while true; do
  # ── 1. 拉取待处理任务（写到临时文件，避免 shell 变量嵌入 JSON 的引号问题）──
  curl -s --max-time 10 "$QUEUE_URL" > "$TMP_RESP" 2>/dev/null || echo '{"jobs":[]}' > "$TMP_RESP"

  count=$("$PYTHON" -c "
import json, sys
try:
    d = json.load(open('$TMP_RESP'))
    print(len(d.get('jobs', [])))
except:
    print(0)
" 2>/dev/null || echo 0)

  if [[ "$count" -gt 0 ]]; then
    echo "[mac_worker] $(date '+%H:%M:%S') 收到 $count 个任务"

    # ── 2. 逐个处理 ───────────────────────────────────────────────────────────
    "$PYTHON" - "$TMP_RESP" "$DONE_URL" "$PYTHON" "$WHISPER_MODEL" <<'PYEOF' || echo "[mac_worker] 处理块出错，继续轮询"
import sys, json, subprocess, tempfile, os
from pathlib import Path
import urllib.request, urllib.error

resp_file = sys.argv[1]
done_url  = sys.argv[2]
python    = sys.argv[3]
model     = sys.argv[4]

try:
    jobs = json.load(open(resp_file)).get('jobs', [])
except Exception as e:
    print(f"  ✗ 解析队列失败: {e}")
    sys.exit(0)

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
    print(f"  处理: {url[:70]}  job_id={job_id}")

    try:
        with tempfile.TemporaryDirectory() as td:
            # 1. yt-dlp 下载音频（优先 chrome cookies，兜底直连）
            audio_out = f"{td}/audio.%(ext)s"
            dl_cmds = [
                ["yt-dlp", "-f", "bestaudio", "--no-playlist",
                 "--cookies-from-browser", "chrome", "-o", audio_out, url],
                ["yt-dlp", "-f", "bestaudio", "--no-playlist",
                 "--cookies-from-browser", "safari", "-o", audio_out, url],
                ["yt-dlp", "-f", "bestaudio", "--no-playlist",
                 "-o", audio_out, url],
            ]
            dl_ok = False
            dl_err = ""
            for cmd in dl_cmds:
                p = subprocess.run(cmd, capture_output=True, text=True)
                if p.returncode == 0:
                    dl_ok = True
                    break
                dl_err = (p.stderr or p.stdout)[-200:]

            if not dl_ok:
                print(f"  ✗ 下载失败: {dl_err[-100:]}")
                post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                      "ok": False, "error": f"download_failed: {dl_err[-100:]}"})
                continue

            audio_files = list(Path(td).glob("audio.*"))
            if not audio_files:
                print(f"  ✗ 未找到音频文件")
                post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                      "ok": False, "error": "no_audio_file"})
                continue

            print(f"  ✓ 下载完成: {audio_files[0].name}")

            # 2. 转换为 16kHz WAV
            wav = f"{td}/audio.wav"
            fr = subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_files[0]), "-vn", "-ac", "1", "-ar", "16000", wav],
                capture_output=True, text=True
            )
            if fr.returncode != 0:
                print(f"  ✗ ffmpeg 失败: {fr.stderr[-100:]}")
                post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                      "ok": False, "error": "ffmpeg_failed"})
                continue

            print(f"  ✓ 音频转换完成，开始 Whisper 转录...")

            # 3. Whisper 转录
            code = f"""
from faster_whisper import WhisperModel
import json
model = WhisperModel({model!r}, device="cpu", compute_type="int8")
segs, info = model.transcribe({wav!r}, vad_filter=True)
text = " ".join(s.text.strip() for s in segs)
print(json.dumps({{"ok": True, "text": text, "lang": info.language}}))
"""
            wp = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=600)
            try:
                wout = json.loads(wp.stdout.strip().splitlines()[-1])
            except Exception as e:
                print(f"  ✗ Whisper 解析失败: {wp.stderr[-100:]}")
                post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                      "ok": False, "error": f"whisper_failed: {wp.stderr[-100:]}"})
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
            print(f"  → 回传结果: {result[:120]}")

    except Exception as e:
        print(f"  ✗ 处理异常: {e}")
        try:
            post_json(done_url, {"job_id": job_id, "run_id": run_id, "url": url,
                                  "ok": False, "error": str(e)[:200]})
        except:
            pass

print("  本轮处理完毕")
PYEOF

  fi

  sleep "$POLL_INTERVAL"
done
