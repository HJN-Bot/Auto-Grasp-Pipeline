# Reference Projects for Content Intelligence Pipeline

These projects are useful references for the local low-token harvest → digest → EPUB pipeline.

## Source Collection

- `miniflux/v2` — RSS reader with REST/Fever APIs. Use as a high-quality feed inbox.
- `huginn/huginn` — agent-based scraping and alerting. Borrow CSS-selector polling ideas.
- `ArchiveBox/ArchiveBox` — durable webpage snapshots. Use to avoid refetching and losing sources.
- `dgtlmoon/changedetection.io` — trigger processing only when pages change.

## Extraction and Token Reduction

- `adbar/trafilatura` — main-content extraction and metadata. Best candidate to add next for cleaner body text and lower token cost.
- `mozilla/readability` — Firefox Reader Mode extraction logic. Good Node-side alternative.
- `codelucas/newspaper4k` — article extraction, keyword, and summary helpers.
- `jina-ai/reader` — URL → LLM-friendly Markdown pattern; useful as optional fallback, not required for local MVP.
- `matthewwithanm/python-markdownify` — HTML → Markdown normalization.

## Bookmarks / Read-it-later

- `sissbruecker/linkding` — self-hosted bookmark manager with REST API and tags. Good canonical queue for saved links.
- `omnivore-app/omnivore` — read-it-later + highlights + labels; useful state-machine pattern.

## Publishing

- `jgm/pandoc` — Markdown → EPUB. Current MVP uses it when installed and writes a fallback note when missing.

## Patterns To Reuse

1. Use RSS/bookmarks/starred repos as structured, low-noise inputs.
2. Cache and hash every URL before extraction.
3. Run readability/trafilatura-style cleaning before any LLM call.
4. Use labels/status fields as pipeline state: `inbox → extracted → selected → published`.
5. Generate Markdown first; EPUB is a deterministic build artifact.
