#!/usr/bin/env python3
"""Local source collection and digest publishing MVP.

This script is intentionally small and deterministic:
- JSON config in, Markdown digest out.
- Optional GitHub starred repository ingestion through `gh` when authenticated.
- URL fetch cache and URL-level deduplication.
- X/Twitter links are metadata/manual-fallback only.
- No paid APIs.
"""
import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


URL_RE = re.compile(r"https?://[^\s<>'\")\]]+")
TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "spm"}
TRACKING_PREFIXES = ("utm_",)
DEFAULT_USER_AGENT = "content-link-harvest-local/0.1"


@dataclass
class Source:
    url: str
    canonical_url: str
    title: str = ""
    body: str = ""
    source_type: str = "web"
    method: str = ""
    priority: int = 0
    quality_score: int = 0
    approx_tokens: int = 0
    selected_tokens: int = 0
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


def read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    host = parsed.netloc.lower()
    if host.endswith(":80") and parsed.scheme == "http":
        host = host[:-3]
    if host.endswith(":443") and parsed.scheme == "https":
        host = host[:-4]
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower()
        if key_l in TRACKING_PARAMS or any(key_l.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        query.append((key, value))
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((parsed.scheme.lower(), host, path, "", urlencode(query), ""))


def extract_urls(text: str) -> List[str]:
    urls = []
    for match in URL_RE.findall(text or ""):
        urls.append(match.rstrip(".,;:!?"))
    return urls


def approx_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def domain_for(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def is_x_url(url: str) -> bool:
    host = domain_for(url)
    return host in {"x.com", "twitter.com", "mobile.twitter.com"} or host.endswith(".twitter.com")


def priority_for(url: str, priority_domains: List[str]) -> int:
    host = domain_for(url)
    for idx, domain in enumerate(priority_domains):
        d = domain.lower().removeprefix("www.")
        if host == d or host.endswith("." + d):
            return max(1, len(priority_domains) - idx)
    return 0


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def meta_content(raw_html: str, names: Iterable[str]) -> str:
    for name in names:
        patterns = [
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']',
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']',
            rf'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']',
        ]
        for pattern in patterns:
            found = re.search(pattern, raw_html, re.I | re.S)
            if found:
                return html.unescape(re.sub(r"\s+", " ", found.group(1)).strip())
    return ""


def title_from_html(raw_html: str) -> str:
    og_title = meta_content(raw_html, ["og:title", "twitter:title"])
    if og_title:
        return og_title
    found = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S)
    if found:
        return html.unescape(re.sub(r"\s+", " ", found.group(1)).strip())
    return ""


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def fetch_url(url: str, cache_dir: Path, timeout: int, refresh: bool = False) -> Tuple[str, str, str]:
    key = cache_key(url)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists() and not refresh:
        cached = read_json(cache_path)
        return cached.get("text", ""), cached.get("title", ""), "cache"

    parsed = urlparse(url)
    if parsed.scheme == "file":
        raw = Path(parsed.path).read_text(encoding="utf-8")
    else:
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read().decode(charset, errors="replace")

    if "<html" in raw[:500].lower() or "<title" in raw[:2000].lower():
        title = title_from_html(raw)
        desc = meta_content(raw, ["description", "og:description", "twitter:description"])
        body = desc + "\n\n" + html_to_text(raw) if desc else html_to_text(raw)
    else:
        title = ""
        body = raw.strip()

    write_json(cache_path, {"url": url, "fetched_at": int(time.time()), "title": title, "text": body})
    return body, title, "fetch"


def fetch_feed_response(url: str, cache_dir: Path, timeout: int, refresh: bool = False) -> Tuple[str, str]:
    key = cache_key(url)
    cache_path = cache_dir / "feeds" / f"{key}.json"
    if cache_path.exists() and not refresh:
        cached = read_json(cache_path)
        return cached.get("text", ""), "feed_cache"

    parsed = urlparse(url)
    if parsed.scheme == "file":
        raw = Path(parsed.path).read_text(encoding="utf-8")
    else:
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read().decode(charset, errors="replace")

    write_json(cache_path, {"url": url, "fetched_at": int(time.time()), "text": raw})
    return raw, "feed_fetch"


def xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def first_child_text(parent: ET.Element, names: Iterable[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(parent):
        if xml_name(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return html.unescape(text)
    return ""


def feed_title(root: ET.Element) -> str:
    if xml_name(root.tag) == "feed":
        return first_child_text(root, ["title"])
    for child in list(root):
        if xml_name(child.tag) == "channel":
            return first_child_text(child, ["title"])
    return ""


def atom_entry_url(entry: ET.Element) -> str:
    fallback = ""
    for child in list(entry):
        if xml_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        if not href:
            continue
        rel = child.attrib.get("rel", "alternate").lower()
        if rel == "alternate":
            return href
        if not fallback:
            fallback = href
    return fallback


def rss_item_url(item: ET.Element) -> str:
    link = first_child_text(item, ["link"])
    if link:
        return link
    guid = first_child_text(item, ["guid"])
    return guid if guid.startswith(("http://", "https://")) else ""


def feed_item_body(item: ET.Element) -> str:
    parts = [
        first_child_text(item, ["description", "summary", "content", "encoded"]),
        first_child_text(item, ["pubDate", "published", "updated"]),
    ]
    clean_parts = []
    for part in parts:
        if not part:
            continue
        clean = html_to_text(part) if "<" in part and ">" in part else re.sub(r"\s+", " ", part).strip()
        if clean:
            clean_parts.append(clean)
    return "\n".join(clean_parts)


def parse_feed_sources(feed_url: str, raw_xml: str, limit: int, priority: int, method: str) -> List[Source]:
    root = ET.fromstring(raw_xml)
    title = feed_title(root)
    entries = list(root) if xml_name(root.tag) == "feed" else []
    if xml_name(root.tag) != "feed":
        entries = []
        for child in list(root):
            if xml_name(child.tag) == "channel":
                entries = [item for item in list(child) if xml_name(item.tag) == "item"]
                break
        if not entries:
            entries = [item for item in list(root) if xml_name(item.tag) == "item"]

    sources: List[Source] = []
    for entry in entries:
        if len(sources) >= limit:
            break
        url = atom_entry_url(entry) if xml_name(root.tag) == "feed" else rss_item_url(entry)
        if not url:
            continue
        item_title = first_child_text(entry, ["title"]) or url
        published = first_child_text(entry, ["pubDate", "published", "updated"])
        metadata = {"feed_url": feed_url}
        if title:
            metadata["feed_title"] = title
        if published:
            metadata["published"] = published
        sources.append(
            Source(
                url=url,
                canonical_url=normalize_url(url),
                title=item_title,
                body=feed_item_body(entry),
                source_type="rss_feed",
                method=method,
                priority=priority,
                metadata=metadata,
            )
        )
    return sources


def rss_feed_sources(config: Dict, base_dir: Path, cache_dir: Path, timeout: int, refresh: bool) -> Tuple[List[Source], List[str]]:
    sources: List[Source] = []
    warnings: List[str] = []
    for idx, feed_cfg in enumerate(config.get("rss_feeds", []), 1):
        if not isinstance(feed_cfg, dict) or not feed_cfg.get("url"):
            warnings.append(f"rss_feed_skipped:{idx}: missing url")
            continue
        feed_url = str(feed_cfg["url"])
        if "://" not in feed_url:
            feed_path = (base_dir / feed_url).resolve()
            feed_url = feed_path.as_uri()
        try:
            limit = int(feed_cfg.get("limit", 20))
            priority = int(feed_cfg.get("priority", 0))
            if limit <= 0:
                continue
            raw_xml, method = fetch_feed_response(feed_url, cache_dir, timeout, refresh)
            sources.extend(parse_feed_sources(feed_url, raw_xml, limit, priority, method))
        except (ET.ParseError, URLError, OSError, UnicodeError, ValueError) as exc:
            warnings.append(f"rss_feed_failed:{feed_url}: {str(exc)[:200]}")
    return sources, warnings


def x_metadata_source(url: str, manual_text: str = "") -> Source:
    parsed = urlparse(url)
    post_id = ""
    found = re.search(r"/status(?:es)?/(\d+)", parsed.path)
    if found:
        post_id = found.group(1)
    title = f"X/Twitter post {post_id}" if post_id else "X/Twitter link"
    source = Source(
        url=url,
        canonical_url=normalize_url(url),
        title=title,
        body=manual_text.strip(),
        source_type="x",
        method="manual_metadata" if manual_text else "metadata_only",
        metadata={"manual_fallback": "Paste tweet/thread text or screenshots for full extraction."},
    )
    if not manual_text:
        source.errors.append("x_manual_fallback_required")
    return source


def score_source(source: Source, priority_domains: List[str]) -> Source:
    source.priority = max(source.priority, priority_for(source.canonical_url, priority_domains))
    source.approx_tokens = approx_tokens("\n".join([source.title, source.body]))
    char_score = min(40, len(source.body) // 80)
    title_score = 8 if source.title else 0
    method_score = 12 if source.method in {"fetch", "cache", "github_starred", "feed_fetch", "feed_cache"} else 2
    priority_score = source.priority * 10
    penalty = 20 if source.errors else 0
    source.quality_score = max(0, priority_score + char_score + title_score + method_score - penalty)
    return source


def load_manual_text(config: Dict, url: str) -> str:
    manual = config.get("manual_text", {})
    return str(manual.get(url) or manual.get(normalize_url(url)) or "")


def links_from_config(config: Dict, base_dir: Path) -> List[str]:
    links = list(config.get("links", []))
    for rel in config.get("input_files", []):
        path = (base_dir / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        links.extend(extract_urls(path.read_text(encoding="utf-8")))
    for item in config.get("manual_sources", []):
        if isinstance(item, dict) and item.get("url"):
            links.append(item["url"])
    return links


CommandRunner = Callable[[List[str]], subprocess.CompletedProcess]


def default_runner(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def gh_is_authenticated(runner: CommandRunner = default_runner) -> bool:
    if runner is default_runner and not shutil.which("gh"):
        return False
    try:
        result = runner(["gh", "auth", "status"])
    except Exception:
        return False
    return result.returncode == 0


def github_starred_sources(limit: int, runner: CommandRunner = default_runner) -> Tuple[List[Source], List[str]]:
    warnings = []
    if limit <= 0:
        return [], warnings
    if not gh_is_authenticated(runner):
        return [], ["github_stars_skipped: gh missing or not authenticated"]

    sources: List[Source] = []
    page = 1
    while len(sources) < limit:
        cmd = ["gh", "api", "-X", "GET", "/user/starred", "-f", "per_page=100", "-f", f"page={page}"]
        try:
            result = runner(cmd)
        except Exception as exc:
            warnings.append(f"github_stars_failed: {exc}")
            break
        if result.returncode != 0:
            warnings.append(f"github_stars_failed: {(result.stderr or result.stdout).strip()[:200]}")
            break
        try:
            repos = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            warnings.append(f"github_stars_parse_failed: {exc}")
            break
        if not repos:
            break
        for repo in repos:
            url = repo.get("html_url")
            if not url:
                continue
            topics = repo.get("topics") or []
            body_parts = [
                repo.get("description") or "",
                "Topics: " + ", ".join(topics) if topics else "",
                f"Language: {repo.get('language')}" if repo.get("language") else "",
            ]
            sources.append(
                Source(
                    url=url,
                    canonical_url=normalize_url(url),
                    title=repo.get("full_name") or repo.get("name") or url,
                    body="\n".join(part for part in body_parts if part),
                    source_type="github_starred_repo",
                    method="github_starred",
                    metadata={"stars": str(repo.get("stargazers_count", ""))},
                )
            )
            if len(sources) >= limit:
                break
        page += 1
    return sources, warnings


def collect_sources(config: Dict, config_path: Path, runner: CommandRunner = default_runner) -> Tuple[List[Source], List[str]]:
    base_dir = config_path.parent
    cache_dir = Path(config.get("cache_dir", ".cache/local_harvest"))
    if not cache_dir.is_absolute():
        cache_dir = (base_dir / cache_dir).resolve()
    priority_domains = list(config.get("priority_domains", []))
    timeout = int(config.get("fetch_timeout_seconds", 12))
    refresh = bool(config.get("refresh_cache", False))
    warnings: List[str] = []
    collected: List[Source] = []

    for url in links_from_config(config, base_dir):
        canonical = normalize_url(url)
        manual_text = load_manual_text(config, url)
        if is_x_url(canonical):
            collected.append(x_metadata_source(url, manual_text))
            continue
        source = Source(url=url, canonical_url=canonical)
        try:
            body, title, method = fetch_url(canonical, cache_dir, timeout, refresh)
            source.body = body
            source.title = title or canonical
            source.method = method
        except (URLError, OSError, UnicodeError, ValueError) as exc:
            source.title = canonical
            source.method = "fetch_failed"
            source.errors.append(str(exc)[:200])
            if manual_text:
                source.body = manual_text.strip()
                source.method = "manual_text"
        collected.append(source)

    gh_cfg = config.get("github_stars", {})
    if gh_cfg.get("enabled"):
        stars, star_warnings = github_starred_sources(int(gh_cfg.get("limit", 30)), runner)
        collected.extend(stars)
        warnings.extend(star_warnings)

    feed_sources, feed_warnings = rss_feed_sources(config, base_dir, cache_dir, timeout, refresh)
    collected.extend(feed_sources)
    warnings.extend(feed_warnings)

    deduped: Dict[str, Source] = {}
    for source in collected:
        source = score_source(source, priority_domains)
        existing = deduped.get(source.canonical_url)
        if existing is None or source.quality_score > existing.quality_score:
            deduped[source.canonical_url] = source
    return list(deduped.values()), warnings


def select_for_budget(sources: List[Source], token_budget: int, per_source_token_limit: int) -> Tuple[List[Source], List[Source]]:
    selected: List[Source] = []
    skipped: List[Source] = []
    remaining = token_budget
    ranked = sorted(sources, key=lambda s: (-s.quality_score, -s.priority, s.canonical_url))
    for source in ranked:
        needed = min(source.approx_tokens, per_source_token_limit)
        if needed <= remaining:
            source.selected_tokens = needed
            selected.append(source)
            remaining -= needed
        else:
            skipped.append(source)
    return selected, skipped


def excerpt(text: str, token_limit: int) -> str:
    char_limit = max(120, token_limit * 4)
    clean = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(clean) <= char_limit:
        return clean
    return clean[:char_limit].rsplit(" ", 1)[0].rstrip() + "..."


def render_markdown(config: Dict, selected: List[Source], skipped: List[Source], warnings: List[str]) -> str:
    token_budget = int(config.get("token_budget", 4000))
    total_candidate_tokens = sum(source.approx_tokens for source in selected + skipped)
    selected_tokens = sum(source.selected_tokens for source in selected)
    lines = [
        "# Local Source Digest",
        "",
        "## Token Budget",
        f"- Budget: {token_budget}",
        f"- Candidate approx tokens: {total_candidate_tokens}",
        f"- Selected approx tokens: {selected_tokens}",
        f"- Remaining approx tokens: {max(0, token_budget - selected_tokens)}",
        f"- Selected sources: {len(selected)}",
        f"- Skipped sources: {len(skipped)}",
        "",
    ]
    if warnings:
        lines.extend(["## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    lines.append("## Priority Sources")
    for idx, source in enumerate(selected, 1):
        lines.extend(
            [
                f"### {idx}. {source.title or source.canonical_url}",
                f"- URL: {source.canonical_url}",
                f"- Type: {source.source_type}",
                f"- Method: {source.method or '(none)'}",
                f"- Quality score: {source.quality_score}",
                f"- Approx tokens used: {source.selected_tokens}",
            ]
        )
        if source.metadata.get("manual_fallback"):
            lines.append(f"- Manual fallback: {source.metadata['manual_fallback']}")
        if source.errors:
            lines.append(f"- Needs attention: {'; '.join(source.errors)}")
        body = excerpt(source.body, source.selected_tokens)
        lines.extend(["", body or "(No extracted body. Add manual text in config.)", ""])

    if skipped:
        lines.append("## Skipped Due To Budget")
        for source in skipped:
            lines.append(f"- score={source.quality_score} tokens={source.approx_tokens} {source.canonical_url}")
        lines.append("")

    lines.append("## Manual Follow-Up")
    manual = [source for source in selected + skipped if source.errors or source.method in {"metadata_only", "fetch_failed"}]
    if not manual:
        lines.append("- None")
    else:
        for source in manual:
            lines.append(f"- {source.canonical_url}: add full text, screenshots, transcript, or corrected URL.")
    lines.append("")
    return "\n".join(lines)


def maybe_build_epub(markdown_path: Path, epub_path: Path) -> str:
    if not shutil.which("pandoc"):
        fallback = epub_path.with_suffix(".epub.fallback.txt")
        fallback.write_text(
            "pandoc was not found, so EPUB generation was skipped.\n"
            f"Markdown digest is available at: {markdown_path}\n",
            encoding="utf-8",
        )
        return f"pandoc_missing:{fallback}"
    result = subprocess.run(["pandoc", str(markdown_path), "-o", str(epub_path)], capture_output=True, text=True)
    if result.returncode != 0:
        fallback = epub_path.with_suffix(".epub.fallback.txt")
        fallback.write_text((result.stderr or result.stdout or "pandoc failed").strip(), encoding="utf-8")
        return f"pandoc_failed:{fallback}"
    return f"epub:{epub_path}"


def run(config_path: Path, output_dir: Optional[Path] = None, build_epub: bool = False) -> Dict:
    config = read_json(config_path)
    if output_dir is None:
        output_dir = Path(config.get("output_dir", "output"))
        if not output_dir.is_absolute():
            output_dir = (config_path.parent / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sources, warnings = collect_sources(config, config_path)
    selected, skipped = select_for_budget(
        sources,
        int(config.get("token_budget", 4000)),
        int(config.get("per_source_token_limit", 900)),
    )
    markdown = render_markdown(config, selected, skipped, warnings)
    digest_path = output_dir / str(config.get("digest_filename", "local-source-digest.md"))
    digest_path.write_text(markdown, encoding="utf-8")

    epub_status = ""
    if build_epub or config.get("build_epub"):
        epub_status = maybe_build_epub(digest_path, output_dir / digest_path.with_suffix(".epub").name)

    report = {
        "ok": True,
        "digest": str(digest_path),
        "epub_status": epub_status,
        "candidate_sources": len(sources),
        "selected_sources": len(selected),
        "skipped_sources": len(skipped),
        "selected_tokens": sum(source.selected_tokens for source in selected),
        "warnings": warnings,
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Collect high-quality local sources and publish a Markdown digest.")
    parser.add_argument("--config", required=True, help="Path to JSON config.")
    parser.add_argument("--out-dir", help="Override output directory.")
    parser.add_argument("--epub", action="store_true", help="Build EPUB with pandoc when available.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable run report.")
    args = parser.parse_args(argv)

    report = run(Path(args.config).resolve(), Path(args.out_dir).resolve() if args.out_dir else None, args.epub)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(report["digest"])
        if report.get("epub_status"):
            print(report["epub_status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
