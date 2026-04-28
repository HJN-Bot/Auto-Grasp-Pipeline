import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import local_harvest


class LocalHarvestTests(unittest.TestCase):
    def test_extract_and_normalize_urls(self):
        text = "Read https://example.com/a?utm_source=x&b=1#frag and https://example.com/a?b=1."
        urls = local_harvest.extract_urls(text)
        self.assertEqual(len(urls), 2)
        self.assertEqual(local_harvest.normalize_url(urls[0]), "https://example.com/a?b=1")
        self.assertEqual(local_harvest.normalize_url(urls[1]), "https://example.com/a?b=1")

    def test_x_url_uses_manual_fallback(self):
        source = local_harvest.x_metadata_source(
            "https://x.com/someone/status/12345",
            "Manual tweet text",
        )
        self.assertEqual(source.source_type, "x")
        self.assertEqual(source.method, "manual_metadata")
        self.assertEqual(source.title, "X/Twitter post 12345")
        self.assertEqual(source.errors, [])

    def test_budget_selects_highest_quality_sources(self):
        high = local_harvest.Source(
            url="https://github.com/a/b",
            canonical_url="https://github.com/a/b",
            title="high",
            body="a" * 1000,
            method="fetch",
        )
        low = local_harvest.Source(
            url="https://low.example/item",
            canonical_url="https://low.example/item",
            title="low",
            body="b" * 1000,
            method="fetch",
        )
        for source in (high, low):
            local_harvest.score_source(source, ["github.com"])
        selected, skipped = local_harvest.select_for_budget([low, high], 300, 300)
        self.assertEqual(selected[0].canonical_url, "https://github.com/a/b")
        self.assertEqual(skipped[0].canonical_url, "https://low.example/item")

    def test_github_starred_sources_via_mocked_gh(self):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if "page=1" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    json.dumps(
                        [
                            {
                                "html_url": "https://github.com/acme/tool",
                                "full_name": "acme/tool",
                                "description": "Useful local tool",
                                "topics": ["cli", "local"],
                                "language": "Python",
                                "stargazers_count": 42,
                            }
                        ]
                    ),
                    "",
                )
            return subprocess.CompletedProcess(cmd, 0, "[]", "")

        sources, warnings = local_harvest.github_starred_sources(1, runner)
        self.assertEqual(warnings, [])
        self.assertEqual(sources[0].title, "acme/tool")
        self.assertIn("Useful local tool", sources[0].body)

    def test_rss_feed_sources_use_cache_and_normalized_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = Path(__file__).parent / "fixtures" / "sample-feed.xml"
            config = {
                "rss_feeds": [{"url": fixture.as_uri(), "limit": 5, "priority": 7}],
                "priority_domains": [],
                "github_stars": {"enabled": False},
                "cache_dir": str(root / "cache"),
            }
            sources, warnings = local_harvest.collect_sources(config, root / "config.json")
            self.assertEqual(warnings, [])
            self.assertEqual(len(sources), 2)
            canonical_urls = {source.canonical_url for source in sources}
            self.assertIn("https://example.com/articles/feed-item?b=1", canonical_urls)
            feed_item = next(source for source in sources if source.title == "Deterministic Feed Item")
            self.assertEqual(feed_item.priority, 7)
            self.assertEqual(feed_item.method, "feed_fetch")
            self.assertEqual(feed_item.metadata["feed_title"], "Local Fixture Feed")

            cached_sources, cached_warnings = local_harvest.collect_sources(config, root / "config.json")
            self.assertEqual(cached_warnings, [])
            self.assertTrue(all(source.method == "feed_cache" for source in cached_sources))

    def test_parse_atom_feed_sources(self):
        raw_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Atom Fixture</title>
          <entry>
            <title>Atom Item</title>
            <link href="https://example.com/atom-item?utm_campaign=test" rel="alternate" />
            <updated>2026-04-28T10:00:00Z</updated>
            <summary>Atom summary text.</summary>
          </entry>
        </feed>"""
        sources = local_harvest.parse_feed_sources("file:///tmp/atom.xml", raw_xml, 10, 5, "feed_fetch")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].canonical_url, "https://example.com/atom-item")
        self.assertEqual(sources[0].title, "Atom Item")
        self.assertEqual(sources[0].metadata["feed_title"], "Atom Fixture")

    def test_run_writes_digest_from_file_url_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "page.html"
            page.write_text(
                "<html><head><title>Fixture Page</title>"
                "<meta name='description' content='Short useful summary'></head>"
                "<body><h1>Fixture Page</h1><p>" + ("Local content. " * 80) + "</p></body></html>",
                encoding="utf-8",
            )
            config = {
                "links": [page.as_uri(), "https://x.com/person/status/9"],
                "manual_text": {"https://x.com/person/status/9": "Thread text"},
                "priority_domains": ["example.com"],
                "github_stars": {"enabled": False},
                "token_budget": 500,
                "per_source_token_limit": 300,
                "cache_dir": str(root / "cache"),
                "output_dir": str(root / "out"),
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            report = local_harvest.run(config_path)
            digest = Path(report["digest"]).read_text(encoding="utf-8")
            self.assertIn("# Local Source Digest", digest)
            self.assertIn("Fixture Page", digest)
            self.assertIn("X/Twitter post 9", digest)

    def test_run_writes_digest_from_file_rss_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = Path(__file__).parent / "fixtures" / "sample-feed.xml"
            config = {
                "rss_feeds": [{"url": fixture.as_uri(), "limit": 2, "priority": 6}],
                "priority_domains": ["docs.python.org"],
                "github_stars": {"enabled": False},
                "token_budget": 500,
                "per_source_token_limit": 250,
                "cache_dir": str(root / "cache"),
                "output_dir": str(root / "out"),
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            report = local_harvest.run(config_path)
            digest = Path(report["digest"]).read_text(encoding="utf-8")
            self.assertIn("Deterministic Feed Item", digest)
            self.assertIn("https://example.com/articles/feed-item?b=1", digest)


if __name__ == "__main__":
    unittest.main()
