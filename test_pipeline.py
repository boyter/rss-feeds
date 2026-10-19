"""The decision layer: who wins when sources disagree, and what may be deleted.

These tests guard the invariant the whole pipeline is built on: no code path may
remove a feed, drop a tag a human decided, or erase a harvested fact unless a
human decided that specific change. Verdict precedence and tag precedence are
where that invariant is actually implemented, so they are where a silent reorder
does damage — and a reorder is exactly what an innocent-looking edit produces.

Run:  python3 -m unittest
"""

import json
import os
import unittest

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

    def test_our_inability_to_decode_is_not_evidence_of_death(self):
        # dieworkwear.com and thecyberwire.com were both deleted by exactly this
        # mistake: brotli has no decoder in the standard library.
        verdict, reason = self.verdict({"status": 200, "undecodable": "br"})
        self.assertEqual((verdict, reason), ("flag", "undecodable:br"))


class TagPrecedence(unittest.TestCase):
    """vocab.merge_tags is the only copy of this rule; rebuild and classify share it."""

    def setUp(self):
        self.vocab = {"topic:security", "topic:ai", "type:publication", "type:vendor-blog",
                      "type:personal-blog", "region:uk", "language:fr"}

    def merge(self, keep, override, suggested):
        return vocab_mod.merge_tags(keep, override, suggested, self.vocab)[0]

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
        # the type facet, so the other candidate never reaches the merge.
        _, problems = vocab_mod.merge_tags(["type:vendor-blog"], ["type:publication"], [], self.vocab)
        self.assertEqual(problems, [])

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


@unittest.skipUnless(os.path.exists("draft.jsonl") and os.path.exists("feeds.json"),
                     "run classify.py first")
class ProductIsConsistent(unittest.TestCase):
    """feeds.json must be exactly what the tooling says it is.

    This is the check that turns "we fixed the precedence" into "it is still
    true of the 2,450 feeds we shipped". It reads the working files and writes
    nothing.
    """

    def setUp(self):
        self.vocab = vocab_mod.load()
        self.feeds = {f["url"]: f for f in json.load(open("feeds.json", encoding="utf-8"))}
        self.draft = {}
        with open("draft.jsonl", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                self.draft[r["url"]] = r

    def test_every_written_feed_matches_the_merge(self):
        wrong = []
        for url, feed in self.feeds.items():
            d = self.draft.get(url)
            if d is None:
                continue
            tags, _ = vocab_mod.merge_tags(feed.get("tags") or [], d.get("final") or [],
                                           d.get("suggested") or [], self.vocab)
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


if __name__ == "__main__":
    unittest.main()
