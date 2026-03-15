# OpenClaw x n8n x Auto-Grasp handoff (Draft)

## Goal
Dashboard 灵感链接（YouTube/XHS/X/公众号）一键进入 n8n webhook，抓取后回传给 OpenClaw 生成标准总结，自动写入 Feishu Wiki（AI Collection/AI观点）+ GitHub。

## Existing Entry
- Dashboard endpoint: `POST /api/harvest/trigger`
- Payload:
```json
{ "links": ["..."], "language": "zh+en", "action": "harvest" }
```
- Webhook source config:
  - secret: `n8n_harvest_webhook`
  - or pass `endpoint` in request body

## Proposed n8n output payload -> OpenClaw
```json
{
  "ok": true,
  "run_id": "n8n-20260315-001",
  "items": [
    {
      "source_type": "youtube|xhs|x|wechat",
      "source_url": "...",
      "title": "...",
      "transcript": "...",
      "language": "zh",
      "meta": {"author":"...","published_at":"..."}
    }
  ]
}
```

## OpenClaw post-process
1. 读取 `items[].transcript`
2. 按模板 `templates/ai_collection_summary_template.md` 生成摘要
3. 写入 Feishu Wiki 固定页（AI Collection / AI观点）
4. 同步写入 GitHub 每日总结目录（`summaries/YYYY-MM-DD/*.md`）
5. 回写 Dashboard：Feishu/GitHub link

## Feishu target (fixed)
- Space: AI Collection
- Page channel: AI观点（如用户未指定则默认此页）

## Governance
- High-risk actions require approval
- External publishing disabled by default
- All runs must keep source link + run_id for audit
