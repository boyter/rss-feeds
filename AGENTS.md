# AGENTS.md — rss-feeds

Tagged lists of RSS feeds. The deliverable is **data**: `feeds.json` is the
product, everything else is tooling that keeps it honest. No build, no test
suite, no dependency install — every script here is Python 3 standard library
only.

```
feeds.json      the list: one feed per line
TAGS.md         the tag vocabulary — the single source of truth for tags
vocab.py        reads TAGS.md; classify.py and rebuild.py validate against it
harvest.py      fetches every feed, records title/description/items/liveness
triage.py       decides keep / flag / remove from the harvest
removals.py     regenerates REMOVED.md from two git revisions
classify.py     proposes tags per feed (rules) and applies hand decisions
review.py       prints hosts that still need a human decision
decide.py       appends hand decisions to overrides.jsonl, rejecting bad ones
rebuild.py      writes feeds.json from all of the above (dry run by default)
overrides.jsonl hand-made tag decisions: one host or one URL per line
spam.jsonl      hand-curated removals with a reason (spam, junk, superseded)
add.py          propose new feeds, verify them by fetching, merge them in
candidates.jsonl  proposed additions: {"url": ..., "tags": [...]}
probe_results.jsonl  what add.py fetched (generated; folded into harvest.jsonl)
BLOCKED_CANDIDATES.md  additions we could not verify, and dead ends not to retry
```

## The pipeline

```bash
python3 harvest.py --limit 40     # smoke test first
python3 harvest.py                # resumable; writes harvest.jsonl
python3 harvest.py --retry-failed # re-fetch only the URLs that are not feeds
python3 triage.py                 # writes triage.jsonl, REMOVED.md
python3 classify.py               # writes draft.jsonl
python3 review.py --sort feeds    # what a human still has to decide
python3 review.py --sort feeds --batch 0 --tsv   # one line per host, cheapest to read
python3 decide.py decisions.txt   # append hand decisions, validated
python3 rebuild.py                # report only
python3 rebuild.py --write        # writes feeds.json.new; nothing else changes
python3 rebuild.py --apply        # replaces feeds.json, after you have read the .new
python3 rebuild.py --strict       # same as report, but exits 1 if any tag would be
                                  # stripped or resolved by priority - a gate for CI
```

Order matters: harvest before triage, triage before rebuild. `feeds.json` is the
product, so `--apply` is deliberately a separate, explicit step from `--write`.

## feeds.json format

One feed per line, sorted by host then path, so a PR diff shows the feed that
changed and nothing else:

```json
[
{"url": "https://example.com/feed.xml", "tags": ["topic:security", "type:publication", "region:uk"], "title": "Example Security"},
{"url": "https://example.org/feed", "tags": ["topic:programming", "type:personal-blog"]}
]
```

- `url` and `tags` are required. `title` is present when the harvest found one;
  it is the human-readable name of the feed, and it is what makes a list of
  2,000 URLs browsable.
- `tags` must come from TAGS.md. A tag that is not in TAGS.md is rejected by
  `classify.py` (printed to stderr) and stripped by `rebuild.py`.
- No `failCount` / `lastCheckTime`. Those were written by the old `check.py`
  (now removed), whose status test (`code >= 200 or code <= 299`) is always
  true, so they measured only reachability. Liveness now lives in
  `harvest.jsonl`.

## Tags

Four facets, described in full in TAGS.md: `topic:`, `type:`, `region:`,
`language:`. Every feed gets at least one `topic:` and **exactly one `type:`**. When the
sources disagree — a feed already carrying `type:vendor-blog` while a rule
suggests `type:personal-blog` — `rebuild.py` keeps one by priority (a hand
override beats a tag already in the file, which beats a rule's guess) and
reports the conflict instead of writing both.
`region:` reflects editorial focus, not where the publisher is registered.
`language:` is omitted for English, with one exception (translated feeds, see
TAGS.md).

Adding a tag means adding it to TAGS.md in the same change, with the same PR.
The old flat vocabulary had 68 tags and 80 combinations, two of which covered
70% of the file (`programming, technology` on 842 feeds). Do not reintroduce
catch-alls.

## Hand decisions: overrides.jsonl

Write them with `decide.py`, which refuses a line with a tag outside TAGS.md,
no `topic:`, or two `type:`s, and writes nothing unless the whole batch is
valid:

```text
# decisions.txt — key, then tags, then optional path=tag rules; # starts a comment
bellingcat.com        topic:journalism topic:security type:publication
darknet.org.uk        topic:security type:publication /category/mena=region:middle-east
https://example.com/feed.xml  topic:ai type:personal-blog
```

What the file itself holds, in JSON:

```json
{"key": "bellingcat.com", "tags": ["topic:journalism", "topic:security", "type:publication"],
 "pathTags": {"/category/mena": ["region:middle-east"], "/category/africa": ["region:africa"]}}
{"key": "https://example.com/feed.xml", "tags": ["topic:ai", "type:personal-blog"]}
```

A key with no slash is a **host**: it applies to every feed on that host.
Write it without `www.` — `classify.py` strips it from both sides, and a rule
keyed `www.example.com` used to match nothing in silence.
`pathTags` adds tags to the feeds whose URL contains the given substring, which
is how a site's category feeds inherit the site's tags and gain their own.
A key with a slash is one **URL** (matched case-insensitively; a stored key
without a query string also matches a live URL that has one). URL rules win over
host rules.

Prefer host rules: 2,452 feeds sit on 2,052 hosts, and one decision on
`darknet.org.uk` covers 30 feeds.

## What a harvest record claims

`harvest.jsonl` is evidence, so each field states what it actually saw:

- `isFeed` — the body began with XML/RSS/Atom. An HTML page that names a feed
  gets that link in `altFeed` and is still not a feed: swapping a URL in
  `feeds.json` is a human decision, but the lead should not be thrown away.
- `itemCount` — items in the fetched head (the head is capped at 60 KB). It is
  **not** `len(items)`: `items` keeps six titles, and calling the sample a count
  once recorded a 200-item feed as having 6. `itemsSampled` is the sample.
- `charset` — set when the body was not valid UTF-8 and was decoded by declared
  charset, or cp1252 as a last resort. Decoding with `errors="replace"` would
  have stored a mangled title as if the feed had written it that way.
- `truncated` — the stream ended early, or `Content-Encoding` lied about the body
  and the raw bytes were used instead.

A `Content-Encoding` header that disagrees with the body's own magic bytes is
believed **last**: servers and CDNs do send an identity body under a gzip header,
and trusting the header produces an empty body and a live feed recorded dead. If
the magic bytes agree and the stream is merely broken, the empty result stands —
that is our truncation, not a lie. Check the magic with the zlib header checksum,
not a list of two-byte magics: a list once omitted `0x78 0x5e` and wrote off a
real deflate body as binary.

## Rules are heuristics; measure them

`classify.py` prints, at the end of every run, the hosts where a rule's `type:`
disagreed with a hand decision in `overrides.jsonl`. The human won every one of
those, so the rule is the thing to narrow. A rule that keeps losing should be
cut, not defended: the company-subdomain rule matched `dev.` (dev.to is a
community, `dev.<user>.github.io` is a person) and matched personal blogs at
`tech.*` that survived only because an override happened to exist for them.

## Network etiquette

`harvest.py` is the only thing that talks to the internet, and it is polite by
construction: 8 lanes, **each host pinned to one lane** so a domain is never hit
twice at once, a pause between requests, and it resumes from `harvest.jsonl`
instead of re-fetching. A full pass over 2,452 feeds takes ~15 minutes; a
`--retry-failed` pass over the ~300 that are not feeds takes ~6. Do not
change that: the old script used 50 threads with no per-host serialization and
that is not how to ask a stranger's web server for 3,000 things.

`harvest.py` never writes `feeds.json`. It appends to `harvest.jsonl`.

## Removals

`triage.py` proposes; `rebuild.py` applies. Verdicts:

- `remove` — domain does not resolve, permanent 4xx (404/410/451), the URL
  serves HTML rather than a feed, or it is in `spam.jsonl`.
- `flag` (kept) — 401/403/429 and bot challenge pages: the site objects to a
  script, not to readers. Timeouts. Feeds that answer but are empty.
- Duplicates are collapsed on a normalized key (scheme, `www.`, trailing slash
  ignored; feedburner query strings kept).

Everything removed is listed in `REMOVED.md` with a reason, and the previous
file is in git history. When in doubt, flag rather than remove: a false removal
is data loss, a false keep is one dead line.

`triage.py` writes a REMOVED.md describing the *current* file, so after a
rebuild run `python3 removals.py --from <rev-before> --to WORKING` to restore
the record of what actually left, with the reason read from `harvest.jsonl`.

Three things the harvester had to learn the hard way, and must keep handling:

- **JSON feeds** (`/feed.json`, jsonfeed.org) are valid feeds.
- Several sites **compress the response regardless of `Accept-Encoding`** —
  without decoding, a good feed looks like binary and gets written off as
  not-a-feed.
- The byte cap applies to the **decoded** body. `read_body()` inflates as the
  response arrives; capping the compressed read at 60 KB cut a gzip stream in
  half, `gzip.decompress` raised `EOFError` (not an `OSError`, so it escaped the
  handler) and live feeds — ProPublica, The Intercept, PC Gamer, Salon,
  R-bloggers — were recorded as not feeds.
- Some CDNs send **brotli** even when we ask for gzip, and brotli is not in the
  standard library. `harvest.py` then records `isFeed: null` and `undecodable`,
  and `triage.py` **flags** it instead of removing it: our inability to decode a
  body is not evidence that the feed is dead. `dieworkwear.com` and
  `thecyberwire.com` were deleted by exactly this mistake and had to be
  restored, verified with `curl --compressed`.

## Adding feeds

For one feed, append a line with `url` and `tags` from TAGS.md — the harvest
fills `title` from the feed itself, so do not type it by hand. For a batch:

```bash
python3 add.py probe candidates.jsonl     # fetch every candidate
python3 add.py merge candidates.jsonl     # writes feeds.json.new
python3 add.py merge candidates.jsonl --apply
```

A candidate reaches `feeds.json` only if it answered with something that parses
as a feed. Read the titles `add.py probe` prints before merging: the title is
how you catch a wrong URL (an NPR section id that is Technology, not Science)
and a hijacked one (a Medium account renamed to a gaming spam phrase). A
candidate already in the file becomes a line in `overrides.jsonl` instead,
which is how a known feed finally gets its tags.

Sites that 403 the harvester are parked in `BLOCKED_CANDIDATES.md` and stay out
until someone verifies them by hand. That file also lists the dead ends that
should not be retried without finding a new address.

Aim at the gaps. To see what the list is short of:

```bash
python3 -c "import json,collections as c; d=json.load(open('feeds.json')); \print(c.Counter(t for f in d for t in f['tags']).most_common(60))"
```

## Spam detection is a counting problem

`triage.py` looks for SEO-spam vocabulary (casino, jackpot, pharma). The first
version flagged **BBC News and Wired** as casino spam, because one real headline
contained "porn" and another contained "OnlyFans". The rule now: a spam term in
the feed's own **title or description** is damning, but terms in item headlines
only count when there are three or more hits. A content farm's entire feed is
about the thing; a newspaper mentions it once. Keep that distinction when you
widen the word list, or the tool will delete legitimate feeds.
