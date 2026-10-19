"""Append hand-made tag decisions to overrides.jsonl, rejecting bad ones.

A decision is one line of compact text, whitespace or tab separated:

    bellingcat.com    topic:journalism topic:security type:publication
    example.com/feed  topic:ai type:personal-blog          # a URL rule (has a /)
    darknet.org.uk    topic:security type:publication      /category/mena=region:middle-east

The first field is the override key: a host (no slash) applies to every feed on
that host; anything with a slash is one feed URL. A trailing `path=tag` pair
becomes a pathTags rule. A `#` starts a comment.

Every line is checked before it is written: the tags must be in TAGS.md, there
must be at least one topic: and exactly one type:, and a key already in
overrides.jsonl is replaced rather than duplicated. Nothing is written if any
line is bad, so a batch either lands whole or not at all.

Usage:
    python3 decide.py decisions.txt        # or: pbpaste | python3 decide.py -
    python3 decide.py --dry-run decisions.txt
"""

import argparse
import json
import os
import sys

import vocab as vocab_mod
import paths

OVERRIDES = paths.data("overrides.jsonl")


def parse_line(line):
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    parts = line.replace("\t", " ").split()
    key, tags = parts[0], []
    path_tags = {}
    for p in parts[1:]:
        if "=" in p and not p.startswith(("topic:", "type:", "region:", "language:")):
            needle, tag = p.split("=", 1)
            path_tags.setdefault(needle, []).append(tag)
        else:
            tags.append(p)
    return key, tags, path_tags


def check(key, tags, path_tags, voc):
    problems = []
    bad = vocab_mod.validate(tags, voc)
    if bad:
        problems.append(f"not in TAGS.md: {bad}")
    if not vocab_mod.facet(tags, "topic"):
        problems.append("no topic:")
    types = vocab_mod.facet(tags, "type")
    if len(types) != 1:
        problems.append(f"{len(types)} type: tags (need exactly one)")
    for needle, extra in path_tags.items():
        bad = vocab_mod.validate(extra, voc)
        if bad:
            problems.append(f"pathTags[{needle}] not in TAGS.md: {bad}")
    if "/" in key and "://" not in key:
        # A key with a slash is a URL rule, and classify.py matches URL rules
        # against the whole URL. A scheme-less key like "medium.com/feed/x"
        # therefore matches nothing, silently, forever.
        problems.append("URL rule needs a scheme: a key with a slash and no "
                        ":// can never match a feed URL (use a host key, or the "
                        "full https:// URL)")
    if "://" in key and "/" not in key.split("://", 1)[1].rstrip("/"):
        problems.append("URL rule with no path matches one exact URL; a host "
                        "rule (no slash) is usually what is meant")
    if "/" not in key and key.lower().startswith("www."):
        # Not an error - classify.py normalizes it - but the bare host is the
        # form that matches every spelling of the site.
        print(f"  note: {key} -> {key[4:]} (classify.py strips www. from host keys)")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="file of decisions, or - for stdin")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    voc = vocab_mod.load()
    text = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()

    parsed, errors = [], []
    for n, line in enumerate(text.splitlines(), 1):
        try:
            got = parse_line(line)
        except Exception as e:
            errors.append(f"line {n}: cannot parse ({e})")
            continue
        if not got:
            continue
        key, tags, path_tags = got
        problems = check(key, tags, path_tags, voc)
        if problems:
            errors.append(f"line {n} [{key}]: {'; '.join(problems)}")
        parsed.append((key, tags, path_tags))

    if errors:
        print(f"REJECTED, nothing written ({len(errors)} bad line(s)):", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1

    existing = []
    if os.path.exists(OVERRIDES):
        for line in open(OVERRIDES, encoding="utf-8"):
            if line.strip():
                existing.append(json.loads(line))
    by_key = {r["key"].lower(): r for r in existing}

    replaced = 0
    for key, tags, path_tags in parsed:
        rule = {"key": key, "tags": vocab_mod.normalize(tags)}
        if path_tags:
            rule["pathTags"] = path_tags
        if key.lower() in by_key:
            replaced += 1
        by_key[key.lower()] = rule

    order = [r["key"].lower() for r in existing]
    for key, _, _ in parsed:
        if key.lower() not in order:
            order.append(key.lower())
    out = [by_key[k] for k in dict.fromkeys(order)]

    print(f"{len(parsed)} decisions ({replaced} replacing an existing rule) "
          f"-> {OVERRIDES}" + (" [dry run]" if args.dry_run else ""))
    for key, tags, path_tags in parsed:
        extra = f"  +{path_tags}" if path_tags else ""
        print(f"  {key:44s} {' '.join(sorted(tags))}{extra}")
    if args.dry_run:
        return 0
    with open(OVERRIDES, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
