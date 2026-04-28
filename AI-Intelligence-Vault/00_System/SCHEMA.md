# AI Intelligence Vault Schema

This vault follows a Karpathy-style LLM Wiki pattern: plain Markdown, local-first, agent-maintained.

## Layers

1. `10_Raw/` — immutable or lightly-normalized inputs: links, tweets, starred repos, feed captures.
2. `20_Sources/` — one note per source with metadata, quotes, evidence, and extraction status.
3. `30_Concepts/` — durable concept pages maintained by synthesis, not by raw capture order.
4. `40_Playbooks/` — reusable operating procedures and build guides.
5. `50_Synthesis/` — daily/weekly/monthly digests, essays, and book chapters.
6. `60_Feishu_Exports/` — selected Markdown drafts ready to sync to Feishu Wiki.
7. `90_Exports/` — EPUB/PDF/HTML/JSON artifacts.

## Operations

- **ingest**: add source → cache/dedupe → source note → raw index update.
- **query**: answer from Markdown notes first; cite source notes.
- **lint**: find stale notes, orphan concepts, missing source fields, duplicate links.
- **publish**: selected synthesis → Feishu Wiki + EPUB/PDF/HTML + Airtable/Dashboard evidence.

## Source Note Template

```yaml
---
title: 
source_url: 
source_type: article|paper|repo|video|tweet|feed|manual
captured_at: YYYY-MM-DD
status: inbox|processed|synthesized|published
topics: []
quality_score: 
token_estimate: 
---
```

Sections:
- TL;DR
- Key Claims
- Evidence / Quotes
- Links To Concepts
- Follow-up Questions
- Export Status
