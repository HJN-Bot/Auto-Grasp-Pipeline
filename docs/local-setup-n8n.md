# 本地部署 n8n（Mac）

## 方案A：Docker（推荐）
```bash
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -e N8N_HOST=localhost \
  -e N8N_PORT=5678 \
  -e WEBHOOK_URL=http://localhost:5678/ \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

## 方案B：npm 直装
```bash
npm install -g n8n
n8n start
```

## 导入工作流
- 打开 `http://localhost:5678`
- Import from file
- 选择 `n8n/workflows/link-harvest-v1.json`

## 必配变量
- `COLLECT_NOTES_SCRIPT`：`/absolute/path/to/scripts/collect_notes.py`
- `NOTES_OUT_DIR`：`/absolute/path/to/output`
