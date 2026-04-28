# Local Harvest MVP

`scripts/local_harvest.py` is a small deterministic collector for low-token source digests.

## What It Does

- Reads links from JSON config, linked text files, and manual source entries.
- Applies high-quality source priority by trusted domain and per-feed priority.
- Ingests RSS/Atom feeds with stdlib XML parsing and local feed-response caching.
- Optionally ingests GitHub starred repositories with `gh api` when `gh auth status` succeeds.
- Extracts generic URLs with local response cache and canonical URL deduplication.
- Treats X/Twitter URLs as metadata plus manual-text fallback.
- Reports approximate token budget usage.
- Publishes a Markdown digest.
- Builds an EPUB with `pandoc` when available; otherwise writes a fallback note.

It does not call paid APIs.

## Run

```bash
python3 scripts/local_harvest.py --config examples/local-harvest.config.json
```

Build EPUB if `pandoc` is installed:

```bash
python3 scripts/local_harvest.py --config examples/local-harvest.config.json --epub
```

Machine-readable run report:

```bash
python3 scripts/local_harvest.py --config examples/local-harvest.config.json --json
```

## Config Fields

- `links`: explicit URLs.
- `input_files`: local files scanned for URLs.
- `manual_text`: URL-to-text map for blocked pages, X/Twitter, screenshots, or pasted excerpts.
- `manual_sources`: extra tracked URLs.
- `rss_feeds`: RSS/Atom feeds to ingest. Each item supports `url`, `limit`, and `priority`.
- `priority_domains`: trusted source domains, ordered from strongest to weakest. Earlier domains rank higher in the digest.
- `github_stars.enabled`: set `true` to try `gh api /user/starred`.
- `github_stars.limit`: maximum starred repos to add.
- `token_budget`: total approximate digest budget.
- `per_source_token_limit`: maximum approximate tokens per selected source.
- `cache_dir`: local fetch cache.
- `output_dir`: digest output folder.
- `build_epub`: attempts EPUB generation through `pandoc`.

Example feed config:

```json
{
  "rss_feeds": [
    {
      "url": "https://github.blog/feed/",
      "limit": 10,
      "priority": 4
    }
  ]
}
```

Feed URLs may also be local files, including `file://` fixtures for tests or relative paths resolved from the config file directory.

## Source Priority

Use `priority_domains` for sources you would be willing to cite or read first: official docs, primary project blogs, standards bodies, original repositories, or known expert feeds. Put broad aggregators and social links lower unless they reliably point to primary material.

Use `rss_feeds[].priority` when a whole feed is high signal even if item domains vary. URL normalization and deduplication still happen after feed parsing, so the best-scoring copy of a URL wins across explicit links, feeds, manual sources, and GitHub stars.

## X/Twitter Handling

X/Twitter pages are intentionally not scraped in this MVP because access is inconsistent and often requires authentication. The digest records post metadata from the URL and uses `manual_text` when supplied.

## Tests

```bash
python3 -m unittest discover -s tests
```
