# Content Intelligence Pipeline

## Flow

1. Capture: links, bookmarks, tweets, GitHub stars, RSS feeds.
2. Preprocess: normalize URL, dedupe, cache, extract metadata/body, estimate tokens.
3. Select: score by source quality, recency, domain priority, novelty, and relevance.
4. Write: source notes + concept updates + digest.
5. Publish: selected Feishu Wiki page, weekly/monthly EPUB, Dashboard status.

## Cost Rule

Do not send raw pages directly to an LLM. Extract and truncate locally first; send only selected evidence chunks.

## Publishing Rule

Local Markdown is the source of truth. Feishu is the collaboration/presentation layer. EPUB/PDF/HTML are export artifacts.
