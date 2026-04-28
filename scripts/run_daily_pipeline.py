#!/usr/bin/env python3
"""One-command daily local pipeline.

Low-token path:
local_harvest -> render_feishu_digest -> vault_lint -> optional Feishu publish.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "AI-Intelligence-Vault"


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="examples/local-harvest.config.json")
    ap.add_argument("--publish-feishu", action="store_true")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    day = datetime.now().strftime("%Y-%m-%d")
    title = args.title or f"AI信息雷达自动摘要 {day} - Sam"

    harvest = run([sys.executable, "scripts/local_harvest.py", "--config", args.config, "--epub", "--json"])
    report = json.loads(harvest.stdout)
    digest = report["digest"]

    feishu_md = VAULT / "60_Feishu_Exports" / f"{day}-auto-digest.md"
    lint_md = VAULT / "00_System" / "vault-lint-report.md"

    run([sys.executable, "scripts/render_feishu_digest.py", "--input", digest, "--out", str(feishu_md), "--title", title.removesuffix(" - Sam")])
    run([sys.executable, "scripts/vault_lint.py", "--vault", str(VAULT), "--out", str(lint_md)])

    result = {
        "ok": True,
        "harvest": report,
        "feishu_markdown": str(feishu_md),
        "vault_lint": str(lint_md),
        "feishu_url": None,
    }
    if args.publish_feishu:
        pub = run([sys.executable, "scripts/publish_feishu_page.py", "--input", str(feishu_md), "--title", title, "--json"])
        result["feishu_url"] = json.loads(pub.stdout)["url"]

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
