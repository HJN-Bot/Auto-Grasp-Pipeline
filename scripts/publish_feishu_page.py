#!/usr/bin/env python3
"""Create a Feishu Wiki docx page from a Markdown file.

Default target is AI Collection. Keeps content as readable paragraph blocks.
Secrets are read from local OpenClaw secrets files; no secrets in args/logs.
"""
import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

import requests

SECRETS = Path("/Users/jianan/.openclaw/secrets")
BASE = "https://open.feishu.cn"
DEFAULT_AI_COLLECTION_NODE = "GmPywLFEMiTOaakkeRpc43LgnGd"


def chunks(text: str, size: int = 1800) -> List[str]:
    parts = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= size:
            parts.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, size)
        if cut < 400:
            cut = size
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return parts or [""]


def post(path: str, payload: dict, token: Optional[str] = None) -> dict:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(BASE + path, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def get(path: str, params: dict, token: str) -> dict:
    r = requests.get(BASE + path, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def tenant_token() -> str:
    app_id = (SECRETS / "feishu_app_id").read_text().strip()
    app_secret = (SECRETS / "feishu_app_secret").read_text().strip()
    data = post("/open-apis/auth/v3/tenant_access_token/internal", {"app_id": app_id, "app_secret": app_secret})
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu auth failed: {data}")
    return data["tenant_access_token"]


def resolve_space(token: str, parent_node: str) -> tuple[str, str]:
    data = get("/open-apis/wiki/v2/spaces/get_node", {"token": parent_node, "obj_type": "wiki"}, token)
    if data.get("code") != 0:
        raise RuntimeError(f"get_node failed: {data}")
    node = data["data"]["node"]
    return node["space_id"], node.get("node_token") or parent_node


def create_page(token: str, parent_node: str, title: str, markdown: str) -> dict:
    space_id, parent = resolve_space(token, parent_node)
    data = post(
        f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
        {"obj_type": "docx", "node_type": "origin", "parent_node_token": parent, "title": title},
        token,
    )
    if data.get("code") != 0:
        raise RuntimeError(f"create node failed: {data}")
    node = data["data"]["node"]
    doc = node["obj_token"]
    children = [
        {"block_type": 2, "text": {"elements": [{"text_run": {"content": part}, "text_element_style": {}}]}}
        for part in chunks(markdown)
    ]
    inserted = post(f"/open-apis/docx/v1/documents/{doc}/blocks/{doc}/children", {"children": children}, token)
    if inserted.get("code") != 0:
        raise RuntimeError(f"insert blocks failed: {inserted}")
    return {
        "ok": True,
        "title": title,
        "url": f"https://my.feishu.cn/wiki/{node['node_token']}",
        "node_token": node["node_token"],
        "doc": doc,
        "space_id": space_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Markdown file to publish")
    parser.add_argument("--title", required=True, help="Feishu page title; use - Sam suffix")
    parser.add_argument("--parent-node", default=os.environ.get("FEISHU_WIKI_NODE_TOKEN", DEFAULT_AI_COLLECTION_NODE))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.title.endswith("- Sam"):
        raise SystemExit("title must end with '- Sam'")
    markdown = Path(args.input).read_text(encoding="utf-8")
    result = create_page(tenant_token(), args.parent_node, args.title, markdown)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["url"])


if __name__ == "__main__":
    main()
