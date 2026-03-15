# Content Link Harvest Local (n8n + Dify)

本仓库用于本地部署四平台内容抓取与笔记提炼流程：
- 小红书（XHS）
- 公众号（WeChat）
- YouTube
- X/Twitter

目标：输入链接列表 → 自动抓取（或生成补料清单）→ 输出中英双语笔记大纲。

## 架构概览

1. **入口**：n8n Webhook（本地）
2. **平台识别**：按 URL host 分流
3. **抓取策略**：
   - YouTube：字幕 API；失败时本地 `yt-dlp + Whisper`
   - X/Twitter：oEmbed API
   - 小红书/公众号：meta + 补料机制
4. **汇总提炼**：固定模板（控 token）
5. **落地输出**：Markdown 笔记 + 补料清单

## 目录
- `docs/local-setup-n8n.md`：n8n 本地部署
- `docs/local-setup-dify.md`：Dify 本地部署
- `docs/source-strategy.md`：四平台抓取策略
- `n8n/workflows/link-harvest-v1.json`：可导入 n8n 工作流
- `dify/link-harvest-v1.dsl.yml`：可导入 Dify DSL
- `templates/outline_zh_en.md`：统一输出模板
- `scripts/collect_notes.py`：本地抓取/降级脚本（可独立运行）

## 快速开始（本地）
1) 启动 n8n（见 docs）
2) 导入 `n8n/workflows/link-harvest-v1.json`
3) 启动 Dify（见 docs）
4) 导入 `dify/link-harvest-v1.dsl.yml`
5) 调用 webhook：
```bash
curl -X POST http://localhost:5678/webhook/content-harvest \
  -H 'content-type: application/json' \
  -d '{"links":["https://youtu.be/SYuSZIIYOfI","http://xhslink.com/o/AnuAFd0cIu5"],"language":"zh+en"}'
```

## 输出格式（固定）
- 核心主张（1句话）
- 支撑论点（3条以内）
- 中文金句（1条）
- 英文表达（1条）
- 标签（3个）
- 补料清单（若抓取不足）
