#!/usr/bin/env bash
# yt_local_inject.sh
# 本地 YouTube 音频下载 → Whisper 转录 → 直接注入 n8n pipeline
#
# 用法：
#   ./yt_local_inject.sh <youtube_url> [n8n_webhook_url]
#
# 环境变量（可写入 ~/.zshrc）：
#   VENV_PYTHON       - 装了 faster-whisper 的 Python 路径
#   N8N_WEBHOOK_URL   - n8n webhook 地址（默认 http://localhost:5678/webhook/content-harvest）

set -euo pipefail

URL="${1:-}"
WEBHOOK="${2:-${N8N_WEBHOOK_URL:-http://localhost:5678/webhook/content-harvest}}"
PYTHON="${VENV_PYTHON:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3}"
WHISPER_MODEL="${WHISPER_MODEL:-small}"

if [[ -z "$URL" ]]; then
  echo "Usage: $0 <youtube_url> [webhook_url]"
  exit 1
fi

TMP_DIR=$(mktemp -d)
TMP_WAV="$TMP_DIR/audio.wav"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

# ── 1. 下载音频（优先 chrome cookies，本地登录态）────────────────────────────
echo "→ [1/3] 下载音频..."
if yt-dlp -f bestaudio --no-playlist \
    --cookies-from-browser chrome \
    -o "$TMP_DIR/audio.%(ext)s" "$URL" 2>/dev/null; then
  : # chrome cookies 成功
elif yt-dlp -f bestaudio --no-playlist \
    --cookies-from-browser safari \
    -o "$TMP_DIR/audio.%(ext)s" "$URL" 2>/dev/null; then
  : # safari cookies 成功
else
  # 最后尝试 cookies.txt 文件
  COOKIES_FILE="${YOUTUBE_COOKIES:-}"
  if [[ -n "$COOKIES_FILE" && -f "$COOKIES_FILE" ]]; then
    yt-dlp -f bestaudio --no-playlist \
      --cookies "$COOKIES_FILE" \
      -o "$TMP_DIR/audio.%(ext)s" "$URL"
  else
    echo "✗ 音频下载失败：三种 cookie 方式均失败"
    exit 1
  fi
fi

AUDIO_FILE=$(ls "$TMP_DIR"/audio.* 2>/dev/null | head -1)
if [[ -z "$AUDIO_FILE" ]]; then
  echo "✗ 未找到下载的音频文件"
  exit 1
fi
echo "  ✓ 音频：$(basename "$AUDIO_FILE")"

# ── 2. 转换为 16kHz 单声道 WAV ───────────────────────────────────────────────
echo "→ [2/3] 转换格式..."
ffmpeg -y -i "$AUDIO_FILE" -vn -ac 1 -ar 16000 "$TMP_WAV" 2>/dev/null
echo "  ✓ WAV 就绪"

# ── 3. Whisper 转录 ───────────────────────────────────────────────────────────
echo "→ [3/3] Whisper 转录（model=$WHISPER_MODEL）..."
TRANSCRIPT=$("$PYTHON" - "$TMP_WAV" "$WHISPER_MODEL" <<'PYEOF'
import sys
from faster_whisper import WhisperModel
wav_path, model_name = sys.argv[1], sys.argv[2]
model = WhisperModel(model_name, device="cpu", compute_type="int8")
segments, info = model.transcribe(wav_path, vad_filter=True)
print(" ".join(s.text.strip() for s in segments))
PYEOF
)

CHARS=${#TRANSCRIPT}
if [[ "$CHARS" -lt 50 ]]; then
  echo "✗ 转录结果过短（$CHARS 字符），可能失败"
  exit 1
fi
echo "  ✓ 转录完成（$CHARS 字符）"
echo "  预览：${TRANSCRIPT:0:120}..."

# ── 4. 注入 n8n ──────────────────────────────────────────────────────────────
echo "→ 注入 n8n ($WEBHOOK)..."
PAYLOAD=$("$PYTHON" - "$URL" "$TRANSCRIPT" <<'PYEOF'
import sys, json
url, transcript = sys.argv[1], sys.argv[2]
print(json.dumps({
    "links": [url],
    "raw_text": transcript,
    "language": "zh+en"
}, ensure_ascii=False))
PYEOF
)

HTTP_CODE=$(curl -s -o /tmp/yt_inject_resp.json -w "%{http_code}" \
  -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

if [[ "$HTTP_CODE" == "200" ]]; then
  echo "✓ 注入成功（HTTP $HTTP_CODE）"
  cat /tmp/yt_inject_resp.json | "$PYTHON" -c "
import json,sys
d=json.load(sys.stdin)
print('records:', len(d.get('records',[])))
print('outlines:', len(d.get('outlines',[])))
" 2>/dev/null || cat /tmp/yt_inject_resp.json
else
  echo "✗ 注入失败（HTTP $HTTP_CODE）"
  cat /tmp/yt_inject_resp.json
  exit 1
fi
