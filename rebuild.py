"""Rebuild feeds.json from the harvest, triage and tag decisions.

Dry run by default: prints what would change. --write applies it, and writes
REMOVED.md recording every feed that left the file and why.

Output format: one feed per line, sorted by host then path, so a diff of a
future PR shows the feed that changed and nothing else.

    {"url": "...", "title": "...", "tags": ["topic:security", "type:publication"]}

failCount/lastCheckTime are gone: they were written by check.py, whose status
test was always true, and harvest.jsonl now holds real per-feed results.

Usage:
    python3 rebuild.py            # report only
    python3 rebuild.py --write
"""

import argparse
import collections
import json
import sys
import vocab as vocab_mod
from urllib.parse import urlparse


def host_path(url):
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www."), p.path.lower(), p.query.lower())


def norm_key(url):
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    if "feedburner" in host:
        return host + p.path.lower() + "?" + p.query.lower()
    return host + p.path.lower().rstrip("/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write feeds.json.new (safe); use --apply to replace feeds.json")
    ap.add_argument("--apply", action="store_true",
                    help="replace feeds.json in place. Only after reading feeds.json.new.")
    args = ap.parse_args()

    feeds = json.load(open("feeds.json", encoding="utf-8"))
    harvest = {}
    for line in open("harvest.jsonl", encoding="utf-8"):
        try:
            r = json.loads(line)
            harvest[r["url"]] = r
        except json.JSONDecodeError:
            pass
    triage = {}
    for line in open("triage.jsonl", encoding="utf-8"):
        r = json.loads(line)
        triage[r["url"]] = r
    draft = {}
    for line in open("draft.jsonl", encoding="utf-8"):
        r = json.loads(line)
        draft[r["url"]] = r

    vocab = vocab_mod.load()

    out, removed, problems = [], [], []
    seen = {}
    for feed in feeds:
        url = feed["url"]
        key = norm_key(url)
        if key in seen:
            removed.append((url, "duplicate-of:" + seen[key]))
            continue
        t = triage.get(url, {})
        if t.get("verdict") == "remove":
            removed.append((url, t.get("reason", "")))
            continue
        d = draft.get(url, {})
        # Tags already in feeds.json are decisions; the rules add to them, they
        # do not replace them. Rebuild used to overwrite, which silently erased
        # every tag the previous pass had derived from the old flat vocabulary.
        keep = [t for t in feed.get("tags") or [] if t in vocab]
        proposed = d.get("final") or d.get("suggested") or []
        tags = vocab_mod.normalize(sorted(set(keep) | set(t for t in proposed if t in vocab)))
        bad = [t for t in feed.get("tags") or [] if t not in vocab]
        if bad:
            problems.append((url, f"dropped tags not in TAGS.md: {bad}"))
        if not [x for x in tags if x.startswith("topic:")] or \
           not [x for x in tags if x.startswith("type:")]:
            # A live feed with no tags stays in the file. Dropping it would turn
            # a classification gap into data loss.
            problems.append((url, "missing topic or type"))
        rec = {"url": url, "tags": sorted(tags)}
        title = harvest.get(url, {}).get("title") or ""
        if title:
            rec["title"] = title
        seen[key] = url
        out.append(rec)

    out.sort(key=lambda r: host_path(r["url"]))

    print(f"in:  {len(feeds)}")
    print(f"out: {len(out)}")
    print(f"removed: {len(removed)}")
    reasons = collections.Counter(r[1].split(":")[0] for r in removed)
    for k, v in reasons.most_common():
        print(f"   {v:5d} {k}")
    if problems:
        print(f"incomplete tags ({len(problems)}), kept but unclassified:")
        with open("NEEDS_REVIEW.md", "w", encoding="utf-8") as fh:
            fh.write(f"# {len(problems)} feeds kept without a full tag set\n\n"
                     "These are live feeds whose topic or type has not been "
                     "decided yet. Run `python3 review.py` to work through them.\n")
            for url, p in problems:
                fh.write(f"- `{url}`\n")
        for url, p in problems[:20]:
            print(f"   {url} {p}")

    if not args.write and not args.apply:
        print("\ndry run; pass --write for feeds.json.new, --apply to replace feeds.json")
        return 0

    target = "feeds.json" if args.apply else "feeds.json.new"
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("[\n")
        for i, rec in enumerate(out):
            fh.write(json.dumps(rec, ensure_ascii=False))
            fh.write(",\n" if i < len(out) - 1 else "\n")
        fh.write("]\n")

    with open("REMOVED.md", "w", encoding="utf-8") as fh:
        fh.write(f"# Removed from feeds.json\n\n{len(removed)} feeds. "
                 "The previous file is in git history; restore any of these by "
                 "re-adding the line.\n")
        by_reason = collections.defaultdict(list)
        for url, reason in removed:
            by_reason[reason.split(":")[0]].append((url, reason))
        for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            fh.write(f"\n## {reason} ({len(items)})\n\n")
            for url, why in sorted(items):
                fh.write(f"- `{url}` — {why}\n")
    print(f"wrote {target} and REMOVED.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
