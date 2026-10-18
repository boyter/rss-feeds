"""Print host-level review batches so classification is done once per domain.

feeds.json has 3,375 feeds across 2,757 hosts, and a host's feeds almost always
share topic and type. Reviewing hosts instead of feeds cuts the manual work by
the multi-feed domains (securityweek.com alone has 27).

Usage:
    python3 review.py                 # summary of what is left to do
    python3 review.py --batch 0       # print batch 0 (150 hosts)
    python3 review.py --only unclassified
"""

import argparse
import collections
import json
import os
import sys
from urllib.parse import urlparse

BATCH = 150


def host_of(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def load_draft():
    return [json.loads(l) for l in open("draft.jsonl", encoding="utf-8") if l.strip()]


def group(rows):
    hosts = collections.defaultdict(list)
    for r in rows:
        hosts[r["host"]].append(r)
    return hosts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=-1)
    ap.add_argument("--size", type=int, default=BATCH)
    ap.add_argument("--brief", action="store_true",
                    help="host, title, description only - for long batches")
    ap.add_argument("--only", default="unclassified")
    ap.add_argument("--sort", default="host", choices=["host", "feeds"])
    args = ap.parse_args()

    rows = load_draft()
    hosts = group(rows)
    def settled(rs):
        """A host is done when every feed on it has a topic and a type."""
        for r in rs:
            tags = r["final"] or r["suggested"] or []
            if not any(t.startswith("topic:") for t in tags) or \
               not any(t.startswith("type:") for t in tags):
                return False
        return True

    done = {h for h, rs in hosts.items() if settled(rs)}
    # A host with no harvested title/items cannot be judged yet - it is either
    # dead (handled by triage.py) or simply not fetched yet.
    judgeable = {h for h, rs in hosts.items()
                 if any(r["title"] or r["items"] for r in rs)}
    todo = [h for h in sorted(hosts) if h not in done and h in judgeable]
    if args.sort == "feeds":
        # Most feeds per unit of review effort: a decision on darknet.org.uk
        # covers 30 feeds, one on a lone personal blog covers one.
        todo.sort(key=lambda h: (-len(hosts[h]), h))

    if args.batch < 0:
        print(f"{len(hosts)} hosts, {len(done)} decided, {len(todo)} judgeable to review,")
        print(f"  {len(hosts) - len(done) - len(todo)} with no harvest data yet")
        print(f"{(len(todo) + args.size - 1) // args.size} batches of {args.size}")
        counts = collections.Counter()
        for h, rs in hosts.items():
            counts[len(rs)] += 1
        print("feeds-per-host:", dict(sorted(counts.items())[:8]))
        return 0

    chunk = todo[args.batch * args.size:(args.batch + 1) * args.size]
    print(f"# batch {args.batch}: hosts {args.batch * args.size}-{args.batch * args.size + len(chunk) - 1} of {len(todo)}")
    for h in chunk:
        rs = hosts[h]
        unsettled = [r for r in rs
                     if not any(t.startswith("topic:") for t in (r["final"] or r["suggested"] or []))
                     or not any(t.startswith("type:") for t in (r["final"] or r["suggested"] or []))]
        if not unsettled:
            continue
        rs = unsettled
        title = next((r["title"] for r in rs if r["title"]), "(no title)")
        desc = next((r["description"] for r in rs if r["description"]), "")
        items = next((r["items"] for r in rs if r["items"]), [])
        old = sorted({t for r in rs for t in r["oldTags"]})
        paths = [urlparse(r["url"]).path for r in rs]
        print(f"\n### {h}  [{len(rs)} untagged]" if args.brief else f"\n### {h}  [{len(rs)} feed(s)]")
        print(f"    title: {title[:70]}")
        if desc:
            print(f"    desc : {desc[:110]}")
        if items and not args.brief:
            print(f"    items: {' | '.join(i[:44] for i in items[:3])[:150]}")
        if old and not args.brief:
            print(f"    old  : {','.join(old)}")
        if len(rs) > 1 and not args.brief:
            for p in paths[:6]:
                print(f"    path : {p[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
