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
- `scripts/local_harvest.py`：低 token 本地来源收集 + Markdown/EPUB 发布 MVP
- `examples/local-harvest.config.json`：本地收集示例配置
- `docs/local-harvest-mvp.md`：本地 MVP 使用说明
- `docs/reference-projects.md`：可借鉴的开源项目与后续集成方向

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

## 本地来源 Digest MVP

无需外部付费 API，可直接用 JSON 配置收集高优先级来源、RSS/Atom feed、去重、缓存、报告 token 预算并输出 Markdown：

```bash
python3 scripts/local_harvest.py --config examples/local-harvest.config.json
```

如已安装 `pandoc`，可同时生成 EPUB；未安装时会写入 fallback 说明：

```bash
python3 scripts/local_harvest.py --config examples/local-harvest.config.json --epub
```

来源优先级应偏向一手、高质量材料：官方文档、项目博客、标准/规范、原始仓库、作者本人 feed。`priority_domains` 用于按可信域名排序，`rss_feeds[].priority` 用于提升整条高信号 feed；所有来源最终仍按规范化 URL 去重。

### 正文清洗与状态闭环

- HTML 正文抽取优先尝试 `trafilatura`（如已安装），未安装时自动降级到内置 `html_to_text`，确保零依赖可跑。
- 每次运行会生成 `output/source-state.json`，为每条来源记录 `inbox / extracted / selected / synthesized / published` 状态、`run_id`、质量分、token 与错误信息。
- `run_daily_pipeline.py` 的 JSON 输出会包含 `run_id` 与 `state_manifest`，方便后续写回 Airtable/Dashboard 或 Feishu 页面证据区。

可选安装更强正文抽取器：

```bash
python3 -m pip install trafilatura
```
