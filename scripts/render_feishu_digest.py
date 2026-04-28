#!/usr/bin/env python3
"""Render a concise Feishu-readable digest from a local harvest Markdown file.

No LLM calls. Keeps Feishu pages short and readable.
"""
import argparse
import datetime as dt
import re
from pathlib import Path

ITEM_RE = re.compile(r"^###\s+\d+\.\s+(.+)$", re.M)
URL_RE = re.compile(r"^- URL:\s+(.+)$", re.M)
TYPE_RE = re.compile(r"^- Type:\s+(.+)$", re.M)
SCORE_RE = re.compile(r"^- Quality score:\s+(\d+)", re.M)


def split_items(md: str):
    starts = list(ITEM_RE.finditer(md))
    for idx, match in enumerate(starts):
        end = starts[idx + 1].start() if idx + 1 < len(starts) else len(md)
        block = md[match.start():end]
        title = match.group(1).strip()
        url = (URL_RE.search(block).group(1).strip() if URL_RE.search(block) else "")
        typ = (TYPE_RE.search(block).group(1).strip() if TYPE_RE.search(block) else "")
        score = int(SCORE_RE.search(block).group(1)) if SCORE_RE.search(block) else 0
        body = re.sub(r"^[-#].*$", "", block, flags=re.M).strip()
        body = re.sub(r"\n{2,}", "\n", body)
        yield {"title": title, "url": url, "type": typ, "score": score, "body": body[:240]}


def bullet_items(items):
    lines = []
    for i, item in enumerate(items, 1):
        desc = item["body"].replace("\n", " ").strip()
        lines.append(f"{i}. {item['title']}")
        if item["url"]:
            lines.append(f"   - 链接：{item['url']}")
        lines.append(f"   - 类型/分数：{item['type'] or 'source'} / {item['score']}")
        if desc:
            lines.append(f"   - 摘要：{desc[:160]}")
        lines.append("")
    return "\n".join(lines).strip() or "- 暂无"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="AI信息雷达精选摘要")
    ap.add_argument("--source-label", default="local harvest")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    md = Path(args.input).read_text(encoding="utf-8")
    items = sorted(split_items(md), key=lambda x: (-x["score"], x["title"]))[: args.top]
    deep = [x for x in items if any(k in (x["title"] + x["body"]).lower() for k in ["obsidian", "wiki", "agent", "context", "codex", "claude"])]

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"""# {args.title} - Sam

生成时间：{now}
来源：{args.source_label}

## 1. 一句话结论

本轮信息源已完成低 token 筛选，优先关注与 Agent、知识库、上下文工程、内容自动化直接相关的高信号材料。

## 2. 今日高信号 Top {len(items)}

{bullet_items(items)}

## 3. 为什么重要

- 这些来源可以直接反哺本地 Obsidian/Markdown 母库。
- 高分项目会进入 deep-dive candidates，避免信息只被收藏、不被消化。
- 飞书页只保留精选总结，降低阅读负担。

## 4. 值得深入

{bullet_items(deep[:3])}

## 5. 下一步行动

- 把 Top candidate 升级为 source note / concept note。
- 将真正有复用价值的条目同步到 AI Collection 或 AI Solid Knowledge。
- 每周汇总进入 EPUB 章节候选。

## 6. 证据链接

- Local digest: {Path(args.input).resolve()}
"""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
