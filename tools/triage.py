"""Decide what to keep, what to flag, and what to propose for removal.

Nothing here deletes anything. It writes triage.jsonl with a verdict and a
reason per feed, and REMOVED.md as a human-readable proposal. feeds.json is
only rewritten by rebuild.py, and only after the removal list has been read.

Verdicts:
    keep        live feed, or a transient problem we do not punish
    flag       worth keeping but uncertain (bot-blocked, timeout, empty feed)
    remove     dead beyond recovery: domain does not resolve, permanent HTTP
               error, or the URL never served a feed at all

Usage:
    python3 triage.py
"""

import argparse
import collections
import json
import os
import re
import sys
import paths

# A 401/403/429 is the site objecting to a script, not evidence the feed is
# gone. Those feeds stay, flagged, because a reader's feed client will be fine.
BLOCKED = {401, 403, 429}
# 2xx codes that are not a plain 200. A feed server has no reason to pick one of
# these, so when one shows up the body we got is not the body a reader gets.
UNUSUAL_SUCCESS = {201, 202, 203, 204, 205, 206, 207, 208, 226}
# Permanent, and permanent in a way a retry will not fix.
GONE = {404, 405, 410, 451}
# This pass's report: proposed removals and flags, regenerated every run. It is
# deliberately NOT REMOVED.md, which is the committed record of feeds that were
# actually deleted, written by removals.py from git history.
REPORT = paths.data("TRIAGE.md")
DNS_MARKERS = ("Name or service not known", "nodename nor servname",
               "getaddrinfo", "No address associated with hostname")

SPAM_PATTERNS = [
    # Casino / betting / pharma SEO pages wearing a news feed.
    ("casino-seo", ("casino", "kasin", "vegas slots", "pokies", "jackpot",
                    "slots", "betting bonus", "viagra", "cbd oil", "porn",
                    "xxx", "onlyfans")),
    # Empty feeds that answer 200 but contain nothing.
    ("empty-feed", ()),
]

# A real news outlet runs a story about OnlyFans once. A content farm's whole
# feed is that, so the count and the location decide: a spam term in the
# feed's own name or description is damning, but a single headline is not.
ITEM_SPAM_HITS = 3


def spam_hits(text, words):
    return sum(len(re.findall(r"\b%s\b" % re.escape(w), text, re.I)) for w in words)


def load_spam(path=paths.data("spam.jsonl")):
    """Hand-curated removals: {"key": host-or-url-substring, "reason": ...}."""
    rules = []
    if not os.path.exists(path):
        return rules
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            key = r["key"].strip()
            if not key:
                # An empty key is a substring of every URL: one stray "key": ""
                # line would ban the whole list. Refuse the line, say so.
                print(f"spam.jsonl: ignored a rule with an empty key: {r}",
                      file=sys.stderr)
                continue
            rules.append((key.lower(), r.get("reason", "spam")))
    return rules


def spam_hit(url, spam_rules):
    """Is this URL covered by a hand-curated removal? One matcher, shared.

    add.py, rebuild.py and triage.py must agree about what "banned" means or a
    feed hand-removed in one pass re-enters through another door: add.py merge
    never consulted spam.jsonl, so trustwave SpiderLabs was re-added by every
    settle pass and deleted again by rebuild, forever.

    The key is a lowercased substring of the URL: scheme, www. and junk query
    parameters must not let the same feed back in, and a feedburner name can be
    reused by whoever inherits the alias.
    """
    url_l = url.lower()
    for key, reason in spam_rules:
        if key in url_l:
            return reason
    return None


def classify(rec, feed, spam_rules=()):
    status = rec.get("status", 0)
    err = rec.get("error", "")

    reason = spam_hit(rec["url"], spam_rules)
    if reason is not None:
        # "is not None", not truthy: an empty reason is still a human
        # decision, and the pre-refactor loop returned on the match itself.
        # "hand:" not "spam:" - the file holds any hand-curated removal, a
        # superseded or moved feed as much as a content farm.
        return "remove", f"hand:{reason}"

    if rec.get("regressed"):
        # It answered as a feed when we last looked and does not now. Servers 404
        # and 500 for a single request and come back: a YouTube channel feed did
        # that twice while curl fetched a valid feed seconds later, and the
        # verdict was about to be "remove". A false removal is data loss; a false
        # keep is one dead line. A human decides these.
        #
        # This sits above the keyword patterns on purpose. A hand entry in
        # spam.jsonl is a human decision and outranks it; a vocabulary hit is not,
        # and letting it fire first would remove a formerly-live feed on a word
        # while its own status says "this used to work".
        return "flag", f"regressed:{status or 'no-response'}"

    for name, words in SPAM_PATTERNS:
        if not words:
            continue
        meta = f"{rec.get('title', '')} {rec.get('description', '')}"
        items = " ".join(rec.get("items", []))
        if spam_hits(meta, words):
            return "remove", f"spam:{name}:in-feed-name"
        hits = spam_hits(items, words)
        if hits >= ITEM_SPAM_HITS:
            return "remove", f"spam:{name}:{hits}-item-hits"

    if rec.get("undecodable"):
        # We could not decode the body (brotli, no stdlib support). That is our
        # limitation, not the feed's: a reader's client handles it fine.
        return "flag", f"undecodable:{rec['undecodable']}"
    if status in BLOCKED:
        return "flag", f"blocked:{status}"
    if status in GONE:
        return "remove", f"gone:{status}"
    if status == 0:
        if any(m in err for m in DNS_MARKERS):
            return "remove", "dead-domain"
        return "flag", "unreachable"
    if status and status >= 400:
        return "flag", f"http:{status}"
    if not rec.get("isFeed"):
        # A success that is not 200 is a server doing something unusual - a queue,
        # a challenge page, a partial response - so not reading a feed out of it is
        # our failure, not evidence about the URL. blog.jetbrains.com/feed answers
        # 202 with HTML to the harvester and clean RSS to curl --compressed, and
        # falling through here deleted two live feeds.
        if status in UNUSUAL_SUCCESS:
            return "flag", f"challenge:{status}"
        snippet = (rec.get("snippet") or "").lower()
        # A bot challenge is the site refusing a script, not a dead feed: a
        # reader's feed client with cookies or JS gets through.
        if any(m in snippet for m in ("just a moment", "cloudflare", "captcha",
                                      "enable javascript", "access denied",
                                      "are you a robot", "verify you are human",
                                      "request blocked")):
            return "flag", "bot-challenge"
        return "remove", "not-a-feed"
    if not rec.get("items") and not rec.get("title"):
        return "flag", "empty-feed"
    if not rec.get("items"):
        return "flag", "no-items"
    return "keep", "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harvest", default=paths.data("harvest.jsonl"))
    args = ap.parse_args()

    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    spam_rules = load_spam()
    harvest = {}
    for line in open(args.harvest, encoding="utf-8"):
        try:
            r = json.loads(line)
            harvest[r["url"]] = r
        except json.JSONDecodeError:
            pass

    rows, counts = [], collections.Counter()
    for feed in feeds:
        url = feed["url"]
        rec = harvest.get(url)
        if rec is None:
            verdict, reason = "flag", "not-harvested"
            rec = {}
        else:
            verdict, reason = classify(rec, feed, spam_rules)
        counts[f"{verdict}:{reason.split(':')[0]}"] += 1
        rows.append({
            "url": url, "verdict": verdict, "reason": reason,
            "status": rec.get("status", 0), "error": rec.get("error", ""),
            "title": rec.get("title", ""), "isFeed": rec.get("isFeed", False),
            "failCount": feed.get("failCount"),
        })

    with open(paths.data("triage.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"{len(rows)} feeds triaged")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {v:5d} {k}")

    removes = [r for r in rows if r["verdict"] == "remove"]
    flags = [r for r in rows if r["verdict"] == "flag"]
    # Not REMOVED.md. That file is the record of feeds that were actually
    # deleted, written by removals.py from git history, and it is committed
    # because it is provenance. This report is a per-pass to-do list, regenerated
    # every run and mostly flags: running triage.py must never be able to
    # overwrite the record of what the last pass removed.
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("# Proposed removals\n\n")
        fh.write(f"{len(removes)} feeds, from the harvest in harvest.jsonl. "
                 "Nothing has been deleted yet.\n")
        by_reason = collections.defaultdict(list)
        for r in removes:
            by_reason[r["reason"].split(":")[0]].append(r)
        for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            fh.write(f"\n## {reason} ({len(items)})\n\n")
            for r in sorted(items, key=lambda r: r["url"]):
                title = r["title"][:60] if r["title"] else r["error"][:60]
                fh.write(f"- `{r['url']}` — {r['reason']} — {title}\n")
        fh.write(f"\n# Flagged, kept ({len(flags)})\n\n")
        by_reason = collections.defaultdict(list)
        for r in flags:
            by_reason[r["reason"].split(":")[0]].append(r)
        for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            fh.write(f"\n## {reason} ({len(items)})\n\n")
            for r in sorted(items, key=lambda r: r["url"])[:40]:
                title = r["title"][:60] if r["title"] else r["error"][:60]
                fh.write(f"- `{r['url']}` — {r['reason']} — {title}\n")
    print(f"wrote {paths.data('triage.jsonl')} and {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
