# Automation v2 Plan

Goal: keep model token use low while making the information pipeline useful to read.

## Default Daily Flow

1. `local_harvest.py` collects from RSS/GitHub Stars/manual inbox.
2. `render_feishu_digest.py` turns the local digest into a short Feishu-readable Markdown page.
3. `vault_lint.py` checks the local Obsidian vault and suggests promote candidates.
4. Feishu publishing creates/updates a `- Sam` page in AI Collection.
5. Airtable/Dashboard receives run evidence links.

## Model Use Policy

- No model call for fetch, cache, dedupe, scoring, lint, or Feishu template rendering.
- Use cheap/MAE summary only when converting selected evidence into richer synthesis.
- Use native Codex only for code changes or debugging.

## Suggested Cadence

- Daily: RSS + GitHub Stars digest, Feishu short page.
- Weekly: concept synthesis + EPUB build.
- Monthly: curated book chapter package.

## MAE Hook

When needed, submit only selected snippets, not raw pages:

```bash
/Users/jianan/Projects/local-automation-stack/mae-orchestrator/venv/bin/python3 \
  /Users/jianan/.openclaw/workspace/tools/mae_submit.py \
  --type summary \
  --content "Summarize selected digest snippets into Feishu-ready bullets..."
```
