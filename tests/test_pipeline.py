"""The decision layer: who wins when sources disagree, and what may be deleted.

These tests guard the invariant the whole pipeline is built on: no code path may
remove a feed, drop a tag a human decided, or erase a harvested fact unless a
human decided that specific change. Verdict precedence and tag precedence are
where that invariant is actually implemented, so they are where a silent reorder
does damage — and a reorder is exactly what an innocent-looking edit produces.

Run:  python3 -m unittest discover -s tests -p "test_*.py"
"""

import json
import os
import sys
import unittest

# The tools live in tools/; the tests sit beside the product, not in the
# package, so the package stays a set of scripts you can read top to bottom.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

import paths
import decide
import rebuild
import triage
import vocab as vocab_mod


class TriagePrecedence(unittest.TestCase):
    """Order matters here more than any individual rule.

    hand: is a human decision, so it outranks everything. regressed: says "this
    worked last time", which outranks a keyword pattern. Everything below that is
    machine-derived and may only flag, never remove, on evidence that could be a
    bad afternoon.
    """

    def verdict(self, rec, spam=()):
        rec.setdefault("url", "https://example.test/feed")
        return triage.classify(rec, {"url": rec["url"], "tags": []}, list(spam))

    def test_a_hand_removal_outranks_everything(self):
        rec = {"status": 200, "isFeed": True, "regressed": True, "title": "Fine feed"}
        self.assertEqual(self.verdict(rec, [("example.test", "superseded")])[0], "remove")
        self.assertTrue(self.verdict(rec, [("example.test", "superseded")])[1].startswith("hand:"))

    def test_a_feed_that_worked_last_pass_is_never_removed_on_a_word(self):
        # The keyword patterns used to run first, so a formerly-live feed whose
        # title happened to hit the spam vocabulary was deleted while its own
        # record said "this used to work".
        rec = {"status": 404, "regressed": True, "title": "Casino jackpot bonus pharma"}
        verdict, reason = self.verdict(rec)
        self.assertEqual(verdict, "flag")
        self.assertTrue(reason.startswith("regressed:"))

    def test_the_same_feed_with_no_history_is_removed_on_a_word(self):
        rec = {"status": 404, "title": "Casino jackpot bonus pharma"}
        self.assertEqual(self.verdict(rec)[0], "remove")

    def test_a_single_404_on_a_previously_live_feed_is_a_question(self):
        # A YouTube channel feed 404'd for us while curl fetched it seconds
        # later. One bad response is not evidence of a dead feed.
        verdict, reason = self.verdict({"status": 404, "regressed": True})
        self.assertEqual((verdict, reason), ("flag", "regressed:404"))

    def test_a_404_with_no_history_is_removed(self):
        self.assertEqual(self.verdict({"status": 404})[0], "remove")

    def test_a_domain_that_does_not_resolve_is_removed(self):
        verdict, reason = self.verdict({"status": 0, "error": "URLError [Errno -2] Name or service not known"})
        self.assertEqual((verdict, reason), ("remove", "dead-domain"))

    def test_a_timeout_is_flagged_not_removed(self):
        self.assertEqual(self.verdict({"status": 0, "error": "TimeoutError: timed out"})[0], "flag")

    def test_a_bot_challenge_is_flagged_not_removed(self):
        # The site objects to a script, not to readers.
        for code in (401, 403, 429):
            self.assertEqual(self.verdict({"status": code})[0], "flag", code)

    def test_a_success_that_is_not_200_is_our_failure_not_the_feeds(self):
        # blog.jetbrains.com/feed answered 202 with an HTML interstitial to the
        # harvester, and clean RSS to curl --compressed. A 2xx that is not 200 is
        # a server doing something unusual - a queue, a challenge, a partial - so
        # "we could not read it" may only flag. Falling through to not-a-feed
        # deleted two live feeds.
        verdict, reason = self.verdict({"status": 202, "isFeed": False,
                                        "contentType": "text/html"})
        self.assertEqual(verdict, "flag", reason)

    def test_a_plain_200_html_page_is_still_removed(self):
        # The established rule, pinned so the fix above cannot widen into it: a
        # homepage listed as a feed is not a feed.
        verdict, reason = self.verdict({"status": 200, "isFeed": False,
                                        "snippet": "<html><body>Home</body></html>"})
        self.assertEqual((verdict, reason), ("remove", "not-a-feed"))

    def test_our_inability_to_decode_is_not_evidence_of_death(self):
        # dieworkwear.com and thecyberwire.com were both deleted by exactly this
        # mistake: brotli has no decoder in the standard library.
        verdict, reason = self.verdict({"status": 200, "undecodable": "br"})
        self.assertEqual((verdict, reason), ("flag", "undecodable:br"))


class TagPrecedence(unittest.TestCase):
    """vocab.merge_tags is the only copy of this rule; rebuild and classify share it."""

    def setUp(self):
        self.vocab = {"topic:security", "topic:ai", "topic:health", "topic:news",
                      "type:publication", "type:vendor-blog",
                      "type:personal-blog", "region:uk", "language:fr"}

    def merge(self, keep, override, suggested):
        return vocab_mod.merge_tags(keep, override, suggested, self.vocab, "url")[0]

    def merge_host(self, keep, override, suggested):
        return vocab_mod.merge_tags(keep, override, suggested, self.vocab, "host")[0]

    def test_a_hand_decision_is_the_whole_answer_for_the_facets_it_speaks_to(self):
        # One headline mentioning AI put topic:ai on 273 hand-decided feeds, and
        # a re-harvest moved the tags again when the week's headlines changed.
        got = self.merge(["topic:security", "type:publication"],
                         ["topic:security", "type:publication"],
                         ["topic:ai", "type:vendor-blog"])
        self.assertEqual(got, ["topic:security", "type:publication"])

    def test_a_type_only_override_does_not_strip_topics(self):
        # reddit.com says "aggregator" and leaves the topics to pathTags; a feed
        # matching no pathTag must keep what the rules gave it.
        got = self.merge(["topic:security"], ["type:publication"], ["topic:ai"])
        self.assertIn("topic:security", got)
        self.assertIn("topic:ai", got)

    def test_rules_may_still_add_region_and_language(self):
        got = self.merge([], ["topic:security", "type:publication"], ["region:uk", "language:fr"])
        self.assertEqual(got, ["language:fr", "region:uk", "topic:security", "type:publication"])

    def test_exactly_one_type_survives_a_conflict(self):
        # Priority is who said it: override, then the tag already in feeds.json,
        # then a rule. Alphabetical order must never decide this.
        self.assertEqual([t for t in self.merge(["type:vendor-blog"], [], ["type:publication"])
                          if t.startswith("type:")], ["type:vendor-blog"])
        self.assertEqual([t for t in self.merge(["type:vendor-blog"], ["type:publication"], [])
                          if t.startswith("type:")], ["type:publication"])

    def test_a_conflict_is_reported_with_the_source_that_won(self):
        # With no override, the tag already in feeds.json outranks a rule, and
        # the report says which one won so the choice can be argued with.
        _, problems = vocab_mod.merge_tags(["type:vendor-blog"], [], ["type:publication"], self.vocab)
        self.assertTrue(any(p.startswith("conflicting type:") and "from tags in feeds.json" in p
                            for p in problems))
        # An override removes the conflict instead of resolving it: it speaks to
        # the type facet, so the other candidate never reaches the merge. The tag
        # it displaced is still named - one hand decision overwriting another is a
        # decision, not a detail, and it must be visible in the report.
        _, problems = vocab_mod.merge_tags(["type:vendor-blog"], ["type:publication"], [], self.vocab)
        self.assertTrue(any(p.startswith("override replaced") and "type:vendor-blog" in p
                            for p in problems), problems)

    def test_the_writer_never_guesses_the_destructive_scope(self):
        # rebuild.py is the program that ships feeds.json. If it ever defaults a
        # missing overrideScope to "url", a host rule erases human topics again and
        # nothing in the data shows it.
        src = open(os.path.join(paths.ROOT, "tools", "rebuild.py"), encoding="utf-8").read()
        self.assertNotIn('overrideScope") or "url"', src,
                         "a missing scope must default to the less destructive host reading")

    def test_a_host_rule_may_not_erase_a_tag_meant_for_one_feed(self):
        # The npr.org host rule stripped topic:health from the Global Health
        # section feed, and a youtube.com rule stripped topic:ai from a channel
        # about AI research. A host rule generalizes over a whole site, so it may
        # settle what kind of source the site publishes and nothing more.
        got = self.merge_host(["topic:health", "topic:news", "type:publication"],
                              ["topic:news", "type:publication"], ["topic:ai"])
        self.assertIn("topic:health", got)
        self.assertNotIn("topic:ai", got)          # the headline guess still loses

    def test_a_host_rule_still_sets_the_type(self):
        # Otherwise a site-wide decision ("every feed here is a publication")
        # could never correct a stale type on one of its feeds.
        got = self.merge_host(["type:vendor-blog"], ["type:publication"], [])
        self.assertEqual([t for t in got if t.startswith("type:")], ["type:publication"])

    def test_a_url_rule_is_still_the_whole_answer(self):
        # It names this feed, so it replaces what the feed had.
        got = self.merge(["topic:health", "type:publication"],
                         ["topic:news", "type:publication"], [])
        self.assertNotIn("topic:health", got)

    def test_an_unknown_scope_defaults_to_the_less_destructive_reading(self):
        # A draft row written before overrideScope existed, or hand-edited since,
        # reaches the merge without a scope. Guessing "url" there deletes a topic a
        # human chose, silently; guessing "host" can only keep one too many, and a
        # kept-too-many shows up as a reported type conflict.
        got = vocab_mod.merge_tags(["topic:health", "type:publication"],
                                   ["topic:news", "type:publication"], [], self.vocab)[0]
        self.assertIn("topic:health", got)

    def test_a_malformed_source_is_named_not_absorbed(self):
        # A hand-written override with two types would otherwise have one picked
        # alphabetically and the other discarded in silence.
        _, problems = vocab_mod.merge_tags(
            [], ["topic:ai", "type:personal-blog", "type:publication"], [], self.vocab)
        self.assertTrue(any(p.startswith("BAD SOURCE: the override") for p in problems))

    def test_tags_outside_the_vocabulary_are_dropped_and_said_so(self):
        tags, _ = vocab_mod.merge_tags(["topic:not-in-tags-md"], [], [], self.vocab)
        self.assertEqual(tags, [])
        self.assertEqual(vocab_mod.validate(["topic:not-in-tags-md"], self.vocab),
                         ["topic:not-in-tags-md"])

    def test_a_dead_tag_in_a_hand_written_override_is_named_with_its_file(self):
        # A tag removed from TAGS.md vanishes from the output. When it sits in
        # overrides.jsonl that is a human decision being lost, and the writer used
        # to check only feeds.json - so this path was silent.
        _, problems = vocab_mod.merge_tags([], ["topic:retired-tag", "type:publication"],
                                           [], self.vocab)
        self.assertTrue(any("overrides.jsonl" in p and "topic:retired-tag" in p
                            for p in problems), problems)

    def test_a_parent_region_is_dropped_when_a_child_is_present(self):
        v = self.vocab | {"region:australia", "region:australia-perth"}
        self.assertEqual(vocab_mod.merge_tags(["region:australia"], [], ["region:australia-perth"], v)[0],
                         ["region:australia-perth"])


class TitleChoice(unittest.TestCase):
    """A worse fetch never erases a better one."""

    def test_a_fresh_title_wins(self):
        self.assertEqual(rebuild.pick_title({"title": "New Name"}, "Old Name"), "New Name")

    def test_a_failed_fetch_keeps_the_title_that_was_read(self):
        # A re-harvest would otherwise have erased 14 titles, every one to a
        # timeout or a 403.
        self.assertEqual(rebuild.pick_title({}, "Old Name"), "Old Name")

    def test_a_mis_decoded_title_does_not_replace_a_clean_one(self):
        self.assertEqual(rebuild.pick_title({"title": "Caf\ufffd\ufffd"}, "Café Security"), "Café Security")

    def test_a_title_from_a_cut_body_does_not_replace_a_complete_one(self):
        # The subtle one: a body the byte cap cut mid-character yields a title
        # with no replacement characters in it, merely shorter than the truth.
        rec = {"title": "Александр Токарев: зам", "charset": "decoded as utf-8, tail cut by the byte cap"}
        self.assertEqual(rebuild.pick_title(rec, "Александр Токарев: заметки"), "Александр Токарев: заметки")

    def test_with_no_previous_title_a_cut_one_is_still_written(self):
        rec = {"title": "Partial", "truncated": "tail cut by the byte cap"}
        self.assertEqual(rebuild.pick_title(rec, ""), "Partial")


class Vocabulary(unittest.TestCase):
    def test_tags_md_is_the_source_of_truth(self):
        v = vocab_mod.load()
        self.assertGreater(len(v), 100)
        self.assertIn("type:publication", v)
        self.assertIn("topic:security", v)

    def test_every_facet_is_represented(self):
        v = vocab_mod.load()
        for facet in vocab_mod.FACETS:
            self.assertTrue(any(t.startswith(facet + ":") for t in v), facet)


class SameFeed(unittest.TestCase):
    """What counts as the same feed, decided in one place.

    The key used to drop the query string except for feedburner hosts, which
    collapsed every YouTube channel feed into one line and every NPR section into
    one feed: add.py refused verified additions as "already present", and a
    rebuild would have deleted the rest. Three scripts each had their own copy of
    the rule, which is how they could disagree.
    """

    def test_a_query_string_can_be_the_whole_identity_of_a_feed(self):
        a = vocab_mod.norm_key("https://www.youtube.com/feeds/videos.xml?channel_id=UCYO")
        b = vocab_mod.norm_key("https://www.youtube.com/feeds/videos.xml?channel_id=UCsX")
        self.assertNotEqual(a, b)

    def test_www_trailing_slash_and_scheme_are_ignored(self):
        for u in ("http://Example.com/feed/", "https://www.example.com/feed",
                  "https://example.com/feed"):
            self.assertEqual(vocab_mod.norm_key(u), "example.com/feed", u)

    def test_a_tracking_parameter_does_not_make_a_second_feed(self):
        self.assertEqual(vocab_mod.norm_key("https://example.com/feed?utm_source=nl"),
                         vocab_mod.norm_key("https://example.com/feed"))

    def test_parameter_order_does_not_make_a_second_feed(self):
        self.assertEqual(vocab_mod.norm_key("https://npr.org/rss/rss.php?id=1019&x=1"),
                         vocab_mod.norm_key("https://npr.org/rss/rss.php?x=1&id=1019"))

    def test_a_query_value_is_not_folded_to_lowercase(self):
        # YouTube channel ids are case-sensitive. Folding the value, which the
        # first version of this key did with query.lower(), could fuse two
        # channels into one feed - and a fused feed is a deleted feed.
        a = vocab_mod.norm_key("https://www.youtube.com/feeds/videos.xml?channel_id=UCsXvk37")
        b = vocab_mod.norm_key("https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVK37")
        self.assertNotEqual(a, b)

    def test_a_parameter_called_source_is_not_cut(self):
        # The tracking list used to include source= and ref=. On an API host those
        # name the feed, not the reader, and cutting them collapses distinct feeds.
        a = vocab_mod.norm_key("https://api.example.com/rss?source=bbc")
        b = vocab_mod.norm_key("https://api.example.com/rss?source=cnn")
        self.assertNotEqual(a, b)
        # Analytics parameters are still cut, which is why the list exists.
        self.assertEqual(vocab_mod.norm_key("https://e.com/rss?utm_medium=email&x=1"),
                         vocab_mod.norm_key("https://e.com/rss?x=1"))

    def test_a_path_is_not_folded_to_lowercase(self):
        # The host is case-insensitive by protocol; the path is not, and a
        # case-sensitive server can serve two different feeds at paths that differ
        # only in case. Folding too much deletes a feed; folding too little shows a
        # duplicate line.
        self.assertNotEqual(vocab_mod.norm_key("https://e.org/feeds/Science.xml"),
                            vocab_mod.norm_key("https://e.org/feeds/science.xml"))

    def test_only_one_copy_of_the_rule_exists(self):
        src = "".join(open(os.path.join(paths.ROOT, "tools", f), encoding="utf-8").read()
                      for f in ("add.py", "rebuild.py", "removals.py"))
        self.assertNotIn("def norm_key", src,
                         "norm_key lives in vocab.py; a second copy can disagree")


class ReportFiles(unittest.TestCase):
    """The per-pass report and the committed provenance are different files.

    triage.py used to write REMOVED.md, so a routine triage run replaced the
    committed record of what had actually been deleted with a list of this
    pass's flags - 432 lines of noise over 20 lines of provenance. Running a
    report must not be able to rewrite history.
    """

    def test_triage_writes_its_report_inside_data(self):
        self.assertEqual(triage.REPORT, paths.data("TRIAGE.md"))
        self.assertTrue(triage.REPORT.startswith(paths.DATA + os.sep))

    def test_triage_never_touches_the_provenance_file(self):
        self.assertNotEqual(triage.REPORT, paths.root("REMOVED.md"))
        src = open(os.path.join(paths.ROOT, "tools", "triage.py"), encoding="utf-8").read()
        self.assertNotIn('paths.root("REMOVED.md")', src,
                         "only removals.py may write REMOVED.md")


@unittest.skipUnless(os.path.exists(paths.data("draft.jsonl"))
                     and os.path.exists(paths.root("feeds.json")),
                     "run classify.py first")
class ProductIsConsistent(unittest.TestCase):
    """feeds.json must be exactly what the tooling says it is.

    This is the check that turns "we fixed the precedence" into "it is still
    true of the 2,450 feeds we shipped". It reads the working files and writes
    nothing.
    """

    def setUp(self):
        self.vocab = vocab_mod.load()
        self.feeds = {f["url"]: f for f in
                      json.load(open(paths.root("feeds.json"), encoding="utf-8"))}
        self.draft = {}
        with open(paths.data("draft.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                self.draft[r["url"]] = r

    def test_the_override_scope_travels_to_the_writer(self):
        # classify.py knows whether the override named this URL or the whole host;
        # rebuild.py only knows what draft.jsonl says. Without the scope the writer
        # treats every host rule as a URL rule and erases per-feed tags.
        missing = [r["url"] for r in self.draft.values()
                   if r.get("final") and not r.get("overrideScope")]
        self.assertEqual(missing, [], "draft.jsonl rows with an override need overrideScope")

    def test_every_written_feed_matches_the_merge(self):
        wrong = []
        for url, feed in self.feeds.items():
            d = self.draft.get(url)
            if d is None:
                continue
            tags, _ = vocab_mod.merge_tags(feed.get("tags") or [], d.get("final") or [],
                                           d.get("suggested") or [], self.vocab,
                                           d.get("overrideScope") or "host")
            if tags != sorted(feed["tags"]):
                wrong.append(url)
        self.assertEqual(wrong, [], f"{len(wrong)} feeds disagree with merge_tags")

    def test_every_feed_has_at_most_one_type(self):
        bad = [u for u, f in self.feeds.items()
               if sum(t.startswith("type:") for t in f["tags"]) > 1]
        self.assertEqual(bad, [])

    def test_no_written_tag_is_outside_the_vocabulary(self):
        bad = [t for f in self.feeds.values() for t in f["tags"] if t not in self.vocab]
        self.assertEqual(bad, [])

    def test_no_title_is_mangled(self):
        bad = [u for u, f in self.feeds.items()
               if f.get("title") and ("\ufffd" in f["title"] or "\x00" in f["title"])]
        self.assertEqual(bad, [])


class TestNewRulesCannotSilentlyRetypeTheProduct(unittest.TestCase):
    """decide.py replaces a rule wholesale, and a NEW host rule may settle
    `type:` for feeds already in feeds.json. Both are legitimate in isolation and
    both deleted decisions in the discovery pass: a drafted `techcrunch.com
    type:personal-blog` retyped feeds filed as publication, and `feeds.npr.org
    type:personal-blog` did it to NPR's podcast feeds. Neither showed up as a
    replacement, because there was no previous rule to replace.
    """

    def problems(self, key, tags, feeds, existing=None):
        return decide.overwrite_problems(key, tags, feeds, existing or {})

    def test_a_new_host_rule_that_retypes_existing_feeds_is_refused(self):
        feeds = [{"url": "https://techcrunch.com/feed/", "tags": ["type:publication"]}]
        got = self.problems("techcrunch.com", ["topic:tech-industry", "type:personal-blog"], feeds)
        self.assertTrue(got, "a new host rule retyped a feed already in the product")
        self.assertIn("type:publication", got[0])

    def test_a_host_rule_matching_what_the_host_already_publishes_is_fine(self):
        feeds = [{"url": "https://techcrunch.com/feed/", "tags": ["type:publication"]}]
        self.assertEqual(self.problems("techcrunch.com", ["topic:tech-industry", "type:publication"], feeds), [])

    def test_a_rule_that_drops_a_tag_the_old_rule_had_is_refused(self):
        old = {"tags": ["topic:software-engineering", "topic:security", "type:vendor-blog"]}
        got = self.problems("github.blog", ["topic:software-engineering", "type:vendor-blog"], [], old)
        self.assertTrue(got, "the old rule's topic:security vanished with no report")
        self.assertIn("topic:security", got[0])

    def test_a_url_rule_does_not_retype_the_whole_host(self):
        feeds = [{"url": "https://example.com/feed/", "tags": ["type:publication"]}]
        self.assertEqual(self.problems("https://example.com/other/feed",
                                       ["topic:news", "type:personal-blog"], feeds), [])


if __name__ == "__main__":
    unittest.main()
