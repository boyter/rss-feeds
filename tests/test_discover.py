"""The candidate layer: a curated list is a lead, never an addition.

discover.py is the only place a stranger's list gets to name a URL that may end
up in feeds.json. What it must never do is (a) let a URL through that was never
fetched and seen to be a feed, (b) decide "the same feed" by anything other than
vocab.norm_key, or (c) lose a lead silently, which is how a list of 1,800 URLs
quietly becomes 1,400 and nobody notices.

Run:  python3 -m unittest discover -s tests -p "test_*.py"
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import discover


def urls_of(pairs):
    return [u for u, _ in pairs]


class TestListParsing(unittest.TestCase):
    def test_bare_url_on_a_line_with_a_markdown_link_is_not_lost(self):
        # The first version gated bare-URL scanning on the line containing no
        # "[", so this URL was never yielded, never counted, and never probed.
        text = "See [Example](https://example.com/feed/) and https://other.example/feed.xml\n"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "list.md")
            open(p, "w", encoding="utf-8").write(text)
            got = urls_of(discover.iter_source_text(p))
        self.assertIn("https://example.com/feed/", got)
        self.assertIn("https://other.example/feed.xml", got,
                      "a bare URL sharing a line with a markdown link was dropped")

    def test_bare_url_is_not_yielded_twice(self):
        text = "[Example](https://example.com/feed/)\n"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "list.md")
            open(p, "w", encoding="utf-8").write(text)
            got = urls_of(discover.iter_source_text(p))
        self.assertEqual(got, ["https://example.com/feed/"])

    def test_heading_is_the_category(self):
        text = "## Security\n- [S](https://example.com/feed.xml)\n"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "list.md")
            open(p, "w", encoding="utf-8").write(text)
            self.assertEqual(list(discover.iter_source_text(p)),
                             [("https://example.com/feed.xml", "Security")])

    def test_opml_on_one_line_still_yields_its_feeds(self):
        # A line-based parser returned nothing for this, and "nothing" looked
        # like an empty source rather than a broken parser.
        text = ('<opml><body><outline text="Tech">'
                '<outline text="A Blog" xmlUrl="https://blog.example/feed.xml"/>'
                '</outline></body></opml>')
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "list.opml")
            open(p, "w", encoding="utf-8").write(text)
            self.assertEqual(list(discover.iter_source_text(p)),
                             [("https://blog.example/feed.xml", "Tech")])

    def test_malformed_opml_falls_back_to_the_regex_scan(self):
        text = ('<opml><body><outline text="A" xmlUrl="https://a.example/feed">'
                '<!-- unclosed -->')
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "list.opml")
            open(p, "w", encoding="utf-8").write(text)
            self.assertEqual([u for u, _ in discover.iter_source_text(p)],
                             ["https://a.example/feed"])


class TestPlausibility(unittest.TestCase):
    def test_an_opml_file_is_not_a_feed(self):
        # A curated README linked its own OPML files. An OPML file is XML that
        # parses, so probe recorded it as a feed and it nearly joined the list.
        ok, why = discover.is_plausible_feed("https://lists.example/countries/UK.opml")
        self.assertFalse(ok)
        self.assertEqual(why, "path")

    def test_github_host_is_not_a_feed(self):
        self.assertFalse(discover.is_plausible_feed("https://github.com/x/y")[0])

    def test_a_feed_identified_by_its_query_survives(self):
        ok, _ = discover.is_plausible_feed(
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC123")
        self.assertTrue(ok)

    def test_a_fragment_is_not_part_of_the_feed(self):
        self.assertEqual(
            discover.clean_url("https://example.com/feed/#:~:text=x"),
            "https://example.com/feed/")


class TestDeduplication(unittest.TestCase):
    def test_the_same_feed_key_is_vocab_norm_key(self):
        # add.py and rebuild.py decide "already present" with vocab.norm_key; a
        # second, different key here would admit a duplicate line that rebuild
        # then collapses, or refuse a feed that is genuinely new.
        self.assertEqual(discover.vocab_mod.norm_key("https://x.com/feed/"),
                         discover.vocab_mod.norm_key("http://www.x.com/feed"))


class TestHomesAreNotFeeds(unittest.TestCase):
    def test_a_bare_homepage_is_a_lead_but_a_named_feed_path_is_not(self):
        self.assertTrue(discover.is_homepage("https://a.example/"))
        self.assertTrue(discover.is_homepage("https://a.example"))
        self.assertTrue(discover.is_homepage("https://a.example/blog"))
        self.assertFalse(discover.is_homepage("https://b.example/feed/"))
        self.assertFalse(discover.is_homepage("https://b.example/index.xml"))


class TestTagCascade(unittest.TestCase):
    """cmd_tag decides what lands in feeds.json for a verified candidate.

    Pinned because a tag written here is permanent: a tag already in feeds.json
    outranks a rule's later guess, so a topic copied from the wrong source is
    never revisited.
    """

    def run_tag(self, cands, probed, feeds=(), overrides=()):
        with tempfile.TemporaryDirectory() as d:
            w = lambda n: os.path.join(d, n)
            for name, rows in (("c.jsonl", cands), ("r.jsonl", probed),
                               ("overrides.jsonl", overrides)):
                with open(w(name), "w", encoding="utf-8") as fh:
                    for r in rows:
                        fh.write(json.dumps(r) + "\n")
            open(w("feeds.json"), "w").write(json.dumps(list(feeds)))
            saved = (discover.CANDIDATES, discover.EXPANDED, discover.LEADS,
                     discover.RESULTS, discover.TAGGED,
                     discover.paths.root, discover.paths.data)
            discover.CANDIDATES, discover.EXPANDED, discover.LEADS = w("c.jsonl"), w("e.jsonl"), w("l.jsonl")
            discover.RESULTS, discover.TAGGED = w("r.jsonl"), w("t.jsonl")
            discover.paths.root = lambda n: w("feeds.json") if n == "feeds.json" else None
            discover.paths.data = lambda n: (w("overrides.jsonl") if n == "overrides.jsonl"
                                             else w(n))
            try:
                discover.cmd_tag(type("A", (), {})())
                out = [json.loads(l) for l in open(w("t.jsonl"))]
            finally:
                (discover.CANDIDATES, discover.EXPANDED, discover.LEADS,
                 discover.RESULTS, discover.TAGGED,
                 discover.paths.root, discover.paths.data) = saved
        return out

    def test_a_sibling_topic_is_not_copied_onto_an_aggregator_channel(self):
        # youtube.com already carries a science channel. A new channel on the
        # same host says nothing about itself, and the sibling's topic is the
        # only thing on offer - taking it would stamp science onto a channel we
        # know nothing about, permanently.
        feeds = [{"url": "https://www.youtube.com/feeds/videos.xml?channel_id=SCI",
                  "tags": ["topic:science", "type:video"]}]
        cands = [{"url": "https://www.youtube.com/feeds/videos.xml?channel_id=NEW",
                  "tags": [], "hostTags": ["topic:science", "type:video"],
                  "hintTopics": [], "hintType": None, "category": ""}]
        probed = [{"url": cands[0]["url"], "isFeed": True, "title": "New Channel",
                   "description": "", "items": []}]
        out = self.run_tag(cands, probed, feeds)
        for r in out:
            self.assertNotIn("topic:science", r["tags"],
                             "a sibling channel's topic was copied onto a different channel")

    def test_a_curated_category_beats_a_channels_own_headlines(self):
        cands = [{"url": "https://www.youtube.com/feeds/videos.xml?channel_id=CRIC",
                  "tags": [], "hostTags": ["topic:science", "type:video"],
                  "hintTopics": ["topic:sport"], "hintType": None, "category": "Cricket"}]
        probed = [{"url": cands[0]["url"], "isFeed": True, "title": "Cricket",
                   "description": "", "items": []}]
        out = self.run_tag(cands, probed, [{"url": "https://www.youtube.com/feeds/videos.xml?channel_id=SCI",
                                            "tags": ["topic:science", "type:video"]}])
        self.assertEqual(len(out), 1, out)
        self.assertIn("topic:sport", out[0]["tags"])
        self.assertNotIn("topic:science", out[0]["tags"])

    def test_a_sibling_topic_still_helps_a_category_feed_of_a_real_site(self):
        feeds = [{"url": "https://example.com/feed/",
                  "tags": ["topic:security", "type:publication"]}]
        cands = [{"url": "https://example.com/feed/cyber/",
                  "tags": [], "hostTags": ["topic:security", "type:publication"],
                  "hintTopics": [], "hintType": None, "category": ""}]
        probed = [{"url": cands[0]["url"], "isFeed": True, "title": "Cyber",
                   "description": "", "items": []}]
        out = self.run_tag(cands, probed, feeds)
        self.assertEqual(len(out), 1, out)
        self.assertIn("topic:security", out[0]["tags"])

    def test_a_host_rule_still_adds_a_topic_on_a_real_site(self):
        # The additive side of the npr.org rule: a host rule may not REPLACE a
        # topic a human gave one feed, but on a site its tags describe the site
        # and so are evidence about a new feed it publishes.
        cands = [{"url": "https://blog.virustotal.com/feed/", "tags": [],
                  "hostTags": [], "hintTopics": [], "hintType": None, "category": ""}]
        probed = [{"url": cands[0]["url"], "isFeed": True, "title": "VirusTotal Blog",
                   "description": "", "items": []}]
        out = self.run_tag(cands, probed, overrides=[
            {"key": "blog.virustotal.com",
             "tags": ["topic:security", "type:vendor-blog"]}])
        self.assertEqual(len(out), 1, out)
        self.assertIn("topic:security", out[0]["tags"])

    def test_a_host_rule_never_adds_a_topic_on_an_aggregator(self):
        cands = [{"url": "https://www.youtube.com/feeds/videos.xml?channel_id=NEW",
                  "tags": [], "hostTags": [], "hintTopics": [], "hintType": None,
                  "category": ""}]
        probed = [{"url": cands[0]["url"], "isFeed": True, "title": "New Channel",
                   "description": "", "items": []}]
        out = self.run_tag(cands, probed, overrides=[
            {"key": "youtube.com", "tags": ["topic:science", "type:video"]}])
        for r in out:
            self.assertNotIn("topic:science", r["tags"],
                             "an aggregator host rule stamped its topic on a channel")

    def test_a_url_rule_a_human_wrote_for_a_proxy_host_is_applied(self):
        # feeds.feedburner.com names a different publisher in each path, so the
        # only honest rule is per-feed - and a per-feed rule that is written and
        # then never looked up leaves the feed stuck in the queue forever.
        url = "http://feeds.feedburner.com/SmittenKitchen"
        cands = [{"url": url, "tags": [], "hostTags": [], "hintTopics": [],
                  "hintType": None, "category": "Food"}]
        probed = [{"url": url, "isFeed": True, "title": "smitten kitchen",
                   "description": "", "items": []}]
        out = self.run_tag(cands, probed, overrides=[
            {"key": url, "tags": ["topic:food", "type:publication"]}])
        self.assertEqual(len(out), 1, out)
        self.assertIn("topic:food", out[0]["tags"])
        self.assertIn("type:publication", out[0]["tags"])

    def test_a_feed_no_rule_or_hint_can_tag_is_queued_not_merged(self):
        cands = [{"url": "https://quiet.example/feed", "tags": [], "hostTags": [],
                  "hintTopics": [], "hintType": None, "category": ""}]
        probed = [{"url": cands[0]["url"], "isFeed": True, "title": "",
                   "description": "", "items": []}]
        self.assertEqual(self.run_tag(cands, probed), [],
                         "an undecidable feed must not reach feeds.json")


if __name__ == "__main__":
    unittest.main()


class TestNamedSites(unittest.TestCase):
    """`pages` turns sites a human names into probe targets.

    Pinned because the alternative is path guessing, which measured 3,754 HTML
    pages against 23 real feeds: a site that serves its feed at /blog/atom.xml
    404s on every guess and teaches nothing. Asking the page is the honest move,
    and this is the step that writes the question - so it must write homepages
    only, and must never fetch.
    """

    def run_pages(self, lines):
        with tempfile.TemporaryDirectory() as d:
            sites = os.path.join(d, "sites.txt")
            out = os.path.join(d, "pages.jsonl")
            with open(sites, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            saved = discover.PAGES
            discover.PAGES = out
            try:
                discover.cmd_pages(type("A", (), {"sites": sites})())
                rows = [json.loads(l) for l in open(out)]
            finally:
                discover.PAGES = saved
        return rows

    def test_a_named_feed_path_is_still_asked_as_a_homepage(self):
        # The invariant: a homepage is a place to look, never a candidate feed.
        # Naming /feed/ does not make it one - the answer comes back in altFeed.
        rows = self.run_pages(["https://bmj.com/rss/bmj_recent.xml"])
        self.assertEqual([r["url"] for r in rows], ["https://bmj.com/"])

    def test_the_same_site_named_twice_asks_once(self):
        rows = self.run_pages(["https://who.int/", "https://who.int",
                               json.dumps({"url": "https://who.int/rss-feeds/news-english.xml"})])
        self.assertEqual([r["url"] for r in rows], ["https://who.int/"])

    def test_a_junk_line_is_counted_not_dropped_in_silence(self):
        # Losing a line silently is how a list of 1,800 becomes 1,400 unnoticed.
        rows = self.run_pages(["not a url", "ftp://example.com/x", "https://a.example/"])
        self.assertEqual([r["url"] for r in rows], ["https://a.example/"])
