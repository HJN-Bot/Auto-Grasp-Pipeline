#!/usr/bin/env python3
"""Lint the local AI Intelligence Vault and suggest promote candidates.

No LLM calls. Designed for cron/MAE preflight.
"""
import argparse
import json
import re
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s)>'\"]+")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.S)

REQUIRED_SOURCE_FIELDS = ["title", "source_url", "source_type", "captured_at", "status"]
PROMOTE_KEYWORDS = ["obsidian", "wiki", "agent", "context", "codex", "claude", "eval", "pipeline"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def frontmatter(md: str) -> dict:
    m = FRONTMATTER_RE.search(md)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip().strip('"')
    return data


def lint(vault: Path) -> dict:
    notes = list(vault.rglob("*.md"))
    source_notes = [p for p in notes if "/20_Sources/" in str(p)]
    raw_notes = [p for p in notes if "/10_Raw/" in str(p)]
    issues = []
    urls = {}
    candidates = []

    for p in notes:
        md = read(p)
        for url in URL_RE.findall(md):
            urls.setdefault(url.rstrip(".,"), []).append(str(p.relative_to(vault)))

    for p in source_notes:
        md = read(p)
        fm = frontmatter(md)
        missing = [f for f in REQUIRED_SOURCE_FIELDS if not fm.get(f)]
        if missing:
            issues.append({"file": str(p.relative_to(vault)), "issue": "missing_frontmatter", "fields": missing})
        text = (fm.get("title", "") + " " + md).lower()
        if any(k in text for k in PROMOTE_KEYWORDS):
            candidates.append({"file": str(p.relative_to(vault)), "reason": "keyword_match"})

    duplicate_urls = {u: ps for u, ps in urls.items() if len(set(ps)) > 1}
    if duplicate_urls:
        issues.append({"issue": "duplicate_urls", "count": len(duplicate_urls), "sample": dict(list(duplicate_urls.items())[:5])})

    raw_without_synthesis = []
    synth_dir = vault / "50_Synthesis"
    synth_text = "\n".join(read(p) for p in synth_dir.rglob("*.md")) if synth_dir.exists() else ""
    for p in raw_notes:
        if p.name not in synth_text:
            raw_without_synthesis.append(str(p.relative_to(vault)))

    return {
        "ok": not issues,
        "vault": str(vault),
        "total_notes": len(notes),
        "source_notes": len(source_notes),
        "raw_notes": len(raw_notes),
        "issues": issues,
        "promote_candidates": candidates[:20],
        "raw_without_synthesis": raw_without_synthesis[:20],
    }


def render_md(report: dict) -> str:
    lines = ["# Vault Lint Report", "", f"Vault: {report['vault']}", f"Total notes: {report['total_notes']}", f"Source notes: {report['source_notes']}", f"Raw notes: {report['raw_notes']}", ""]
    lines.append("## Issues")
    if not report["issues"]:
        lines.append("- None")
    else:
        for issue in report["issues"]:
            lines.append(f"- `{issue.get('file', '(vault)')}`: {issue.get('issue')} {issue.get('fields', '')}")
    lines.append("\n## Promote Candidates")
    if not report["promote_candidates"]:
        lines.append("- None")
    else:
        for c in report["promote_candidates"]:
            lines.append(f"- `{c['file']}` — {c['reason']}")
    lines.append("\n## Raw Without Synthesis")
    if not report["raw_without_synthesis"]:
        lines.append("- None")
    else:
        for f in report["raw_without_synthesis"]:
            lines.append(f"- `{f}`")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default="/Users/jianan/.openclaw/workspace/AI-Intelligence-Vault")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = lint(Path(args.vault))
    if args.json:
        text = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        text = render_md(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(out)
    else:
        print(text)


if __name__ == "__main__":
    main()
