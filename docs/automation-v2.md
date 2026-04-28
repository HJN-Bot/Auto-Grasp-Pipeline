# Automation v2 Plan

Goal: keep model token use low while making the information pipeline useful to read.

## Default Daily Flow

1. `local_harvest.py` collects from RSS/GitHub Stars/manual inbox.
2. `render_feishu_digest.py` turns the local digest into a short Feishu-readable Markdown page.
3. `vault_lint.py` checks the local Obsidian vault and suggests promote candidates.
4. Feishu publishing creates/updates a `- Sam` page in AI Collection.
5. Airtable/Dashboard receives run evidence links.

Each run also writes `output/source-state.json` with a stable URL id and source state:

```text
inbox -> extracted -> selected -> synthesized -> published
```

Use this file as the single per-run source-state manifest for Dashboard evidence, duplicate suppression, and publish gating.

## Model Use Policy

- No model call for fetch, cache, dedupe, scoring, lint, or Feishu template rendering.
- HTML cleaning uses optional local `trafilatura` when installed; otherwise the built-in cleaner keeps the pipeline dependency-light.
- Use cheap/MAE summary only when converting selected evidence into richer synthesis.
- Use native Codex only for code changes or debugging.

## n8n Local Notes

- On this Mac, n8n must be started without the SOCKS proxy env because n8n/undici expects `HTTP_PROXY`/`HTTPS_PROXY` to be `http(s)://`, not `socks5h://`:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy N8N_PORT=5678 n8n start
```

- Imported webhook workflows may register paths in `~/.n8n/database.sqlite` as `webhook_entity.webhookPath`; verify the effective route before Dashboard wiring.
- `n8n/workflows/link-harvest-local-smoke.json` is a no-external-forward smoke workflow for validating raw-text handoff locally before enabling remote OpenClaw/Dashboard callbacks.
- 2026-04-29 smoke finding: workflow import/activation works and n8n listens on 5678, but production webhook registration still returns 404 on this local n8n 2.18.4 setup even though `webhook_entity` has rows. Treat Dashboard webhook wiring as blocked until the effective n8n route is fixed in UI or via a stable n8n config/export path.

## Suggested Cadence

User preference: do not publish a Feishu/Dashboard update every day. Daily reading pressure is too high and wastes tokens/attention.

- Passive collection: at most 2-3 times/week, local-only, no Feishu push by default.
- Feishu readable digest: weekly by default, only if there are enough high-signal items.
- Deep synthesis / Jianan Brain article: weekly or manual-triggered, not automatic daily.
- Monthly: curated EPUB / chapter package.

Recommended default cron shape:

```text
Tue/Fri morning: local harvest + source-state only
Sunday evening: selected weekly Feishu digest + EPUB
Manual trigger: immediate harvest/publish for important links Jianan sends
```

Token rule: no LLM call during passive collection. Only selected weekly synthesis may call MAE/cheap summary, and only on snippets already selected by the local manifest.

## MAE Hook

When needed, submit only selected snippets, not raw pages:

```bash
/Users/jianan/Projects/local-automation-stack/mae-orchestrator/venv/bin/python3 \
  /Users/jianan/.openclaw/workspace/tools/mae_submit.py \
  --type summary \
  --content "Summarize selected digest snippets into Feishu-ready bullets..."
```
