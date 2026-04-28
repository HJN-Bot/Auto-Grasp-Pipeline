# Low Token Pipelines

Low-token pipelines reduce model cost by doing deterministic preprocessing before LLM synthesis.

## Pattern

- Cache raw fetches.
- Strip boilerplate locally.
- Estimate tokens before selection.
- Rank sources before summarization.
- Preserve source links for audit.

## Current Implementation

`content-link-harvest-local/scripts/local_harvest.py`
