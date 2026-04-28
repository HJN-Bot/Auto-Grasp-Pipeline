# 本地部署 n8n（Mac）

✅ 已安装：n8n 2.18.4（npm global）

## 启动
```bash
n8n start
```
访问：`http://localhost:5678`

## 导入工作流
- 打开 `http://localhost:5678`
- Import from file
- 选择 `n8n/workflows/link-harvest-v1.json`

## 与 Python 管线配合
n8n 作为可选的 webhook 入口和定时调度。
日常管线推荐直接用 Python：`python3 scripts/run_daily_pipeline.py`

## 可选环境变量
- `COLLECT_NOTES_SCRIPT`：`/absolute/path/to/scripts/collect_notes.py`
- `NOTES_OUT_DIR`：`/absolute/path/to/output`
