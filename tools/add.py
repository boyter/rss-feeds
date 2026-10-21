"""Add new feeds: propose candidates, verify them by fetching, then merge.

Nothing is added on the strength of a guess. A candidate only reaches feeds.json
if it answers with something that parses as a feed, and the title it reports is
checked against the tags the candidate claimed.

Usage:
    python3 add.py probe candidates.jsonl      # fetch, write probe_results.jsonl
    python3 add.py merge candidates.jsonl          # writes feeds.json.new
    python3 add.py merge candidates.jsonl --apply  # replaces feeds.json

Candidates are one JSON object per line:
    {"url": "...", "tags": ["topic:science", "type:publication", "region:usa"]}
"""

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import harvest
import triage
import vocab as vocab_mod
import paths

RESULTS = paths.data("probe_results.jsonl")


def host_path(url):
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www."), p.path.lower(), p.query.lower())


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def cmd_probe(args):
    cands = read_jsonl(args.candidates)
    urls = [c["url"] for c in cands]
    done = {}
    if os.path.exists(RESULTS) and not args.restart:
        for r in read_jsonl(RESULTS):
            done[r["url"]] = r
    todo = [u for u in urls if u not in done]
    print(f"{len(urls)} candidates, {len(done)} already probed, {len(todo)} to fetch")
    if not todo:
        return 0
    lanes = harvest.build_lanes(todo, harvest.LANES)
    with open(RESULTS, "a", encoding="utf-8") as out:
        import concurrent.futures as futures
        import threading
        lock = threading.Lock()

        def run(lane):
            for url in lane:
                rec = harvest.probe(url)
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
            return None

        with futures.ThreadPoolExecutor(max_workers=len(lanes)) as ex:
            list(ex.map(run, lanes))
    done = {r["url"]: r for r in read_jsonl(RESULTS)}
    ok = [u for u in urls if done.get(u, {}).get("isFeed")]
    print(f"{len(ok)} of {len(urls)} serve a real feed")
    for c in cands:
        r = done.get(c["url"], {})
        if r.get("isFeed"):
            print(f"  OK   {c['url'][:62]:62s} {r.get('title','')[:44]}")
        else:
            print(f"  FAIL {c['url'][:62]:62s} {r.get('status')} {r.get('error') or r.get('snippet','')[:40]}")
    return 0


def cmd_merge(args):
    cands = read_jsonl(args.candidates)
    probed = {r["url"]: r for r in read_jsonl(RESULTS)} if os.path.exists(RESULTS) else {}
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    existing = {vocab_mod.norm_key(f["url"]) for f in feeds}
    voc = vocab_mod.load()
    spam_rules = triage.load_spam()
    # harvest.jsonl is evidence of what the URL is NOW; probe_results is a
    # snapshot that goes stale. A feed that died after being probed was
    # re-merged from an old candidates file and deleted again by rebuild -
    # the same ping-pong as spam, one layer up. Latest record per URL wins.
    hpath = paths.data("harvest.jsonl")
    harvested = {}
    if os.path.exists(hpath):
        for r in read_jsonl(hpath):
            if r.get("url"):
                harvested[vocab_mod.norm_key(r["url"])] = r

    added, skipped = [], []
    for c in cands:
        url = c["url"]
        key = vocab_mod.norm_key(url)
        banned = triage.spam_hit(url, spam_rules)
        if banned is not None:
            # spam.jsonl is a human decision; a stale candidates file must not
            # re-admit what a human removed. Without this, every settle pass
            # re-added the hand-removed feeds and rebuild deleted them again.
            # "is not None": an empty reason is still a decision.
            skipped.append((url, f"banned by spam.jsonl: {banned}"))
            continue
        if key in existing:
            skipped.append((url, "already present"))
            continue
        r = probed.get(url, {})
        if not r.get("isFeed"):
            skipped.append((url, f"not a feed ({r.get('status', 'not probed')})"))
            continue
        h = harvested.get(key)
        if h is not None and not h.get("isFeed"):
            skipped.append((url, f"dead in harvest.jsonl ({h.get('status', '?')}), "
                                 "newer than the probe"))
            continue
        bad = vocab_mod.validate(c["tags"], voc)
        if bad:
            skipped.append((url, f"tags not in TAGS.md: {bad}"))
            continue
        if not vocab_mod.facet(c["tags"], "topic") or not vocab_mod.facet(c["tags"], "type"):
            skipped.append((url, "needs at least one topic: and one type:"))
            continue
        feeds.append({"url": url, "tags": vocab_mod.normalize(c["tags"]),
                      **({"title": r["title"]} if r.get("title") else {})})
        existing.add(key)
        added.append(url)

    feeds.sort(key=lambda f: host_path(f["url"]))
    target = paths.root("feeds.json") if args.apply else paths.root("feeds.json.new")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("[\n")
        for i, f in enumerate(feeds):
            fh.write(json.dumps(f, ensure_ascii=False))
            fh.write(",\n" if i < len(feeds) - 1 else "\n")
        fh.write("]\n")
    print(f"added {len(added)}, skipped {len(skipped)} -> {target}")
    for url, why in skipped:
        print(f"  skip {url[:60]:60s} {why}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("candidates")
    p.add_argument("--restart", action="store_true")
    m = sub.add_parser("merge")
    m.add_argument("candidates")
    m.add_argument("--apply", action="store_true",
                   help="replace feeds.json; without it feeds.json.new is written")
    p.set_defaults(func=cmd_probe)
    m.set_defaults(func=cmd_merge)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
