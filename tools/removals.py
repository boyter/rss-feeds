"""Write REMOVED.md from what actually left feeds.json between two revisions.

triage.py's REMOVED.md describes the current file, so running triage after a
rebuild overwrites the record of the rebuild itself. This reads the two
versions out of git and explains each disappearance from harvest.jsonl, so the
list of what was dropped and why survives the pass that dropped it.

Usage:
    python3 removals.py                       # HEAD~1 -> working tree
    python3 removals.py --from HEAD~2
"""

import argparse
import collections
import json
import re
import subprocess
import paths
import vocab as vocab_mod
from urllib.parse import urlparse


def load_rev(rev):
    out = subprocess.run(["git", "show", f"{rev}:feeds.json"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def loose_key(url):
    """norm_key with runs of slashes collapsed.

    Used to tell a deliberate re-point (//feed.xml -> /feed.xml) apart from a
    removal: the old URL answered with a real feed, so the status-based reason
    has nothing to say about it and it would otherwise be filed under
    "duplicate", which is not what happened.
    """
    return re.sub(r"/+", "/", vocab_mod.norm_key(url))


def reason_for(url, rec, spam_rules=()):
    low = url.lower()
    for key, why in spam_rules:
        if key in low:
            return f"removed by hand: {why}"
    if rec is None:
        return "no harvest record"
    # Status first. A 404 record has no isFeed field either, and checking the
    # response shape before the status called every dead link "non-feed".
    status = rec.get("status", 0)
    if status in (404, 405, 410, 451):
        return f"gone ({status})"
    if status == 0:
        err = rec.get("error", "")
        if "Name or service not known" in err or "getaddrinfo" in err \
           or "No address associated" in err:
            return "domain no longer resolves"
        return f"unreachable ({err[:40]})"
    if status >= 400:
        return f"http {status}"
    if not rec.get("isFeed"):
        snippet = (rec.get("snippet") or "").lower()
        if any(m in snippet for m in ("just a moment", "cloudflare", "captcha",
                                      "access denied", "enable javascript")):
            return "bot challenge page, not a feed"
        return f"served {rec.get('contentType', 'something')} where a feed should be"
    # It answered with a real feed and is still not in the list: it was a
    # duplicate of another entry, collapsed on the normalized key.
    return "duplicate of another entry"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default="HEAD~1")
    ap.add_argument("--to", dest="dst", default="HEAD")
    args = ap.parse_args()

    before = load_rev(args.src)
    try:
        after = load_rev(args.dst)
    except subprocess.CalledProcessError:
        after = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    kept = {vocab_mod.norm_key(f["url"]) for f in after}
    moved_to = {}
    for f in after:
        moved_to.setdefault(loose_key(f["url"]), f["url"])

    harvest = {}
    for line in open(paths.data("harvest.jsonl"), encoding="utf-8"):
        try:
            r = json.loads(line)
            harvest[r["url"]] = r
        except json.JSONDecodeError:
            pass

    spam_rules = []
    try:
        for line in open(paths.data("spam.jsonl"), encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                spam_rules.append((r["key"].lower(), r.get("reason", "")))
    except FileNotFoundError:
        pass

    gone = []
    seen = set()
    for f in before:
        key = vocab_mod.norm_key(f["url"])
        if key in kept:
            continue
        if key in seen:
            gone.append((f["url"], "duplicate of an entry already removed", ""))
            continue
        seen.add(key)
        rec = harvest.get(f["url"])
        moved = moved_to.get(loose_key(f["url"]))
        if moved and moved != f["url"]:
            gone.append((f["url"], f"moved to {moved}", (rec or {}).get("title", "")))
            continue
        gone.append((f["url"], reason_for(f["url"], rec, spam_rules),
                     (rec or {}).get("title", "")))

    by_reason = collections.defaultdict(list)
    for url, reason, title in gone:
        head = "moved" if reason.startswith("moved to ") else \
            reason.split(" (")[0].split(",")[0]
        by_reason[head].append((url, reason, title))

    with open(paths.root("REMOVED.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Removed between {args.src} and {args.dst}\n\n")
        fh.write(f"{len(gone)} of {len(before)} feeds left the list. The previous "
                 "file is in git history; restore any of these by re-adding the line. "
                 "Reasons come from harvest.jsonl, not from a guess.\n")
        for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            fh.write(f"\n## {reason} ({len(items)})\n\n")
            for url, why, title in sorted(items):
                note = title[:60] if title else why
                fh.write(f"- `{url}` — {note}\n")
    print(f"{len(before)} -> {len(after)}; documented {len(gone)} removals in REMOVED.md")
    return 0


if __name__ == "__main__":
    main()
