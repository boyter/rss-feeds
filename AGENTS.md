# AGENTS.md — rss-feeds

Tagged lists of RSS feeds. The deliverable is **data**: `feeds.json` is the
product, everything else is tooling that keeps it honest. Python 3 standard
library only — no build, no dependency install, no test runner to fetch.

```
feeds.json     the list: one feed per line
TAGS.md        the tag vocabulary — the single source of truth for tags
REMOVED.md     which feeds were deleted, and why (provenance; committed)
BLOCKED_CANDIDATES.md  additions we could not verify, and dead ends not to retry
README.md      what the list is for

tools/         harvest.py  fetch every feed; records title/items/liveness
               triage.py   keep / flag / remove from the harvest
               classify.py propose tags (rules) + apply hand decisions
               review.py   print what still needs a human
               decide.py   the only writer of overrides.jsonl, with validation
               rebuild.py  write feeds.json (dry run by default)
               add.py      propose new feeds, verify by fetching, merge them in
               discover.py turn other people's curated lists into candidates
                           (it never fetches a feed and never writes feeds.json)
               removals.py regenerate REMOVED.md from two git revisions
               vocab.py    TAGS.md, tag precedence, the same-feed key
               paths.py    every path in the project, resolved from the repo root

data/          harvest.jsonl  evidence: one record per fetched URL
               overrides.jsonl  hand-made tag decisions
               spam.jsonl       hand-curated removals with a reason
               (generated, gitignored: draft.jsonl triage.jsonl TRIAGE.md
                probe_results.jsonl NEEDS_REVIEW.md)

tests/         test_harvest.py  the byte layer: encodings, caps, decoding
               test_pipeline.py verdict and tag precedence, file consistency
```

**Picking this work up mid-stream? Read `RESUME.md` first** — it records the
current state, the measured yield of every discovery channel, and the landmines
(each one cost a defect). It is a snapshot, so re-derive its numbers with the
commands it gives you rather than trusting them.

Run the tools from the repo root as `tools/x.py`; they find their files through
`paths.py`, so cwd does not matter.

What still needs a human is not in this file, it is a command:
`python3 tools/review.py --sort feeds` prints the feeds that no rule and no
override speaks to. Sites that refuse the harvester live in
`BLOCKED_CANDIDATES.md` and stay out until someone checks them in a browser.

## The invariant

**No code path may remove a feed, drop a tag a human decided, or erase a
harvested fact, unless a human explicitly decided that change.** A feed that
answers with a real feed must never be recorded `isFeed=false`. Our inability to
read a body is not evidence that the feed is dead.

## The pipeline

```bash
python3 tools/harvest.py --limit 40     # smoke test first
python3 tools/harvest.py                # resumable; appends to data/harvest.jsonl
python3 tools/harvest.py --retry-failed # re-fetch only URLs that are not feeds
python3 tools/triage.py                 # writes data/triage.jsonl and data/TRIAGE.md
python3 tools/classify.py               # writes data/draft.jsonl
python3 tools/review.py --sort feeds    # what a human still has to decide
python3 tools/decide.py decisions.txt   # append hand decisions, validated
python3 tools/rebuild.py                # report only
python3 tools/rebuild.py --write        # writes feeds.json.new; nothing else changes
python3 tools/rebuild.py --apply        # replaces feeds.json, after you have read the .new
python3 tools/rebuild.py --strict       # exits 1 if any tag would be stripped or
                                        # resolved by priority — a gate for CI
```

Order matters: harvest before triage, triage before rebuild. `feeds.json` is the
product, so `--apply` is deliberately separate from `--write`.

## feeds.json format

One feed per line, sorted by host then path, so a diff shows the feed that
changed and nothing else. `url` and `tags` are required; `title` is present when
the harvest found one, and it is what makes 2,400 bare URLs browsable. Tags must
come from TAGS.md — anything else is stripped, and the strip is reported with the
file it came from. Liveness lives in `harvest.jsonl`, not in the product.

## Tags

Four facets, described in full in TAGS.md: `topic:`, `type:`, `region:`,
`language:`. Every feed gets at least one `topic:` and **exactly one `type:`**.
`region:` is editorial focus, not the publisher's postcode. `language:` is
omitted for English, with one exception (translated feeds, see TAGS.md).

Adding a tag means adding it to TAGS.md in the same change. The old flat
vocabulary had 68 tags and 80 combinations, two of which covered 70% of the file.
Do not reintroduce catch-alls.

## Hand decisions: overrides.jsonl

Write them with `decide.py`, which refuses a tag outside TAGS.md, a missing
`topic:`, two `type:`s, or a URL key with no scheme (such a key matches nothing,
silently, forever), and writes nothing unless the whole batch is valid. It also
refuses a rule that would **retype feeds already in `feeds.json`**, or that drops
a tag the previous rule for the same key carried, unless `--allow-type-change`
says that change is the decision: a new host rule needs no previous rule to
overwrite something, and a drafted `feeds.npr.org ... type:personal-blog` would
have retyped NPR's podcast feeds with nothing logged as replaced.

```text
bellingcat.com        topic:journalism topic:security type:publication
darknet.org.uk        topic:security type:publication /category/mena=region:middle-east
https://example.com/feed.xml  topic:ai type:personal-blog
```

A key with no slash is a **host** rule, applying to every feed on it; write it
without `www.`. `pathTags` adds tags to feeds whose URL contains a substring,
which is how a site's category feeds inherit the site's tags and gain their own.
A key with a slash is one **URL**. Prefer host rules: 2,454 feeds sit on 2,052
hosts, and one decision on `darknet.org.uk` covers 30 feeds.

Precedence, implemented once in `vocab.merge_tags` and shared by `rebuild.py`
and `classify.py`:

- A hand decision excludes the rules for the facets it speaks to. The rules read
  item headlines, and that is not a decision: one headline mentioning AI put
  `topic:ai` on 273 hand-decided feeds. Rules may still add `region:` and
  `language:`. If a hand-decided feed should carry another topic, put it in the
  override.
- A **URL** rule is the whole answer for the facets it names, so it replaces what
  the feed had — and the displaced tags are reported. `decide.py`'s drop-guard
  compares the **same key**, so a new URL rule that narrows what an older **host**
  rule gave the same feed is not stopped: three rules written in one batch
  collapsed `topic:security topic:software-engineering` to `topic:personal` on
  `blog.adambell.ca`. The only place that shows is the `override replaced N
  tag(s) already in feeds.json` line in `rebuild.py --write` — read it before
  `--apply`, and fix additively by re-writing the rule for the same key.
- A **host** rule generalizes over a whole site, so it may settle only `type:`.
  It may not erase a topic a human gave to one feed: the `npr.org` host rule once
  stripped `topic:health` from the NPR Global Health section feed. Read the other
  way, the same limit stops a host rule from *giving* a topic it has no business
  deciding: `youtube.com` carries `topic:science`, and letting host-rule topics
  tag new feeds made Bon Appétit and Bloomberg Originals science channels.
- With no override, a tag already in `feeds.json` outranks a rule's guess, and a
  type conflict names which source won.
- When a caller does not know what kind of rule fired, the scope defaults to the
  **less destructive** reading (`host`). Guessing `url` deletes a human's topic in
  silence; guessing `host` can only keep one too many, and that is reported.

`classify.py` records which kind of override fired (`overrideScope`) in
`data/draft.jsonl`, because `rebuild.py` is the writer and must apply the same
rule.

## What a harvest record claims

`harvest.jsonl` is evidence, so each field states what it actually saw. The rules
for reading a stranger's bytes live in `harvest.py` next to the code that
implements them; these are the ones that change what you should *do*:

- `isFeed` — the body began with XML/RSS/Atom. An HTML page that names a feed gets
  that link in `altFeed` and is still not a feed; re-pointing the URL is a human
  decision, but the lead should not be thrown away.
- `itemCount` — items in the fetched head (capped at 60 KB), **not** `len(items)`:
  `items` keeps six titles, and calling the sample a count once recorded a
  200-item feed as having 6.
- `charset` — set when the body was not valid UTF-8 and had to be decoded by
  declared charset or cp1252. Never decode with `errors="replace"`: it stores a
  mangled title as if the feed wrote it that way.
- `regressed` — a previous pass said this URL was a feed and this one does not.
  Always pass `--prior` when a run replaces a file you already have.
- `truncated` — the stream ended early, or `Content-Encoding` lied about the body
  and the raw bytes were used instead.

Encoding is trusted in this order: byte order mark, **byte shape**, utf-8,
declared charset, cp1252. The shape check is not paranoia — ASCII written in
UTF-16 or UTF-32 is also valid UTF-8, decodes with no error into
`<?\x00m\x00l\x00…`, and the feed is recorded as not-a-feed. No validity check can
see that. Details, including what is deliberately out of scope, are in the
comments on `encoding_shape`.

## Removals

`triage.py` proposes; `rebuild.py` applies.

- `remove` — domain does not resolve, permanent 4xx (404/410/451), the URL serves
  HTML rather than a feed, or it is in `spam.jsonl`.
- `flag` (kept) — 401/403/429 and bot challenge pages: the site objects to a
  script, not to readers. Timeouts. Feeds that answer but are empty. Brotli we
  cannot decode with the standard library. And **regressions**: a feed that
  answered as a feed before and does not now is flagged, never removed, because
  servers 404 for one request and come back.
- Duplicates are collapsed on `vocab.norm_key`, which folds only what the
  protocols say is insensitive: the host, the scheme, a trailing slash, and the
  order of query parameters. Path case, parameter-name case and query **values**
  are kept — a case-sensitive server can serve two feeds at paths differing only in
  case, and two YouTube channel ids once differed only in case. Folding too much
  deletes a feed; folding too little shows a duplicate line. The query string is
  kept (41 feeds are identified by it), analytics parameters cut. One copy of that
  key, because `add.py`, `rebuild.py` and `removals.py` must agree about what "the
  same feed" means.

When in doubt, flag rather than remove: a false removal is data loss, a false keep
is one dead line. Before removing anything, check it by hand the way a reader's
feed client would:

```bash
curl -sSL --compressed -A "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0" \
     -o /tmp/f.out -w "http=%{http_code} type=%{content_type} size=%{size_download}\n" URL
head -c 300 /tmp/f.out          # and read the <title>, that is how you know what it is
```

`--compressed` is not optional: without it a brotli or gzip site looks like binary
and gets written off as not-a-feed, which is how `dieworkwear.com` and
`thecyberwire.com` were deleted and had to be restored.

Two files, deliberately apart:

- `REMOVED.md` (committed) — what was actually deleted and why. Written only by
  `removals.py --from <rev> --to WORKING`. `rebuild.py` leaves it alone when a
  pass removes nothing.
- `data/TRIAGE.md` (generated) — this pass's proposed removals and flags. Written
  by `triage.py`. It must never land on `REMOVED.md`: a routine report once
  replaced 20 lines of provenance with 432 lines of flags.

Three things the harvester had to learn, and must keep handling: **JSON feeds**
(`/feed.json`, jsonfeed.org) are valid feeds; several sites **compress regardless
of `Accept-Encoding`**, and undecoded a good feed looks like binary and gets
written off as not-a-feed; and the byte cap applies to the **decoded** body,
because capping the compressed read cut gzip streams in half and recorded
ProPublica, The Intercept, PC Gamer and Salon as not feeds.

## Adding feeds

For one feed, append a line to `feeds.json` with `url` and tags from TAGS.md —
the harvest fills `title`. For a batch, put `{"url": ..., "tags": [...]}` lines in
a file of your own naming:

```bash
python3 tools/add.py probe mycandidates.jsonl     # fetch every candidate
python3 tools/add.py merge mycandidates.jsonl     # writes feeds.json.new
python3 tools/add.py merge mycandidates.jsonl --apply
```

A candidate joins only if it answered with something that parses as a feed. Read
the titles `probe` prints before merging: the title is how you catch a wrong URL
(an NPR section id that is Technology, not Science) and a hijacked one (a Medium
account renamed to a gaming spam phrase). A candidate already in the file becomes
a line in `overrides.jsonl` instead, which is how a known feed finally gets its
tags. Sites that 403 the harvester are parked in `BLOCKED_CANDIDATES.md`.

Where candidates come from, and what each channel actually yielded, is in
`DISCOVERY.md`. `tools/discover.py` writes the candidates file; its `tag` step
also writes two reports that must be read before a merge:
`data/DISCOVERY_REVIEW.md` (tags taken from a list heading, a host rule or a
sibling feed rather than from the feed itself) and `data/DISCOVERY_UNTAGGED.md`
(answered with a real feed, but nothing decides its tags — the fix is a host rule
written with `decide.py`).

Aim at the gaps:

```bash
python3 -c "import json,collections as c; d=json.load(open('feeds.json')); \
print(c.Counter(t for f in d for t in f['tags']).most_common(60))"
```

## Spam detection is a counting problem

A spam term in the feed's own **title or description** is damning; terms in item
headlines count only at three or more hits. A content farm's whole feed is about
the thing; a newspaper mentions it once. The first version of this rule flagged
BBC News and Wired as casino spam. Keep the distinction when widening the word
list, or the tool will delete legitimate feeds.

## Tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

Stdlib only, no network: the tests feed `read_body` and `decode_text` synthetic
bytes. `test_pipeline.py` also reads the working files and asserts `feeds.json` is
exactly what `merge_tags` says it is, so a precedence change cannot silently
disagree with the file that shipped.

**A fix to the decoder, the verdict order, or the tag merge arrives with a test
that fails before the fix.** Ten review passes found roughly two dozen defects
here; none of them stay found unless pinned. Each test names the bug it exists
for in a comment. Verify a test by mutating the code on a copy — revert the fix
and only that test should fail.

Rules that must not be duplicated live in one place: `vocab.merge_tags` (tag
precedence), `vocab.norm_key` (the same-feed key), `rebuild.pick_title` (which
title survives). Two copies of a precedence rule is how the review queue starts
lying about what is still undecided.

## Verifying a change did nothing to the product

Any edit to the tooling — a refactor, a move, a precedence change — has to leave
`feeds.json` byte-identical, unless a human explicitly decided a data change in the
same commit:

```bash
python3 tools/classify.py && python3 tools/rebuild.py --write && cmp feeds.json feeds.json.new
```

That is the only honest proof a move is a move. It is also how three of the defects
in this file were found: the diff was supposed to be empty and was not. The pass is
idempotent — a second `classify` + `rebuild --write` produces the same bytes — so a
difference means a rule is reading something that changes between runs (usually
item headlines, which is a reason to pin the feed with an override).

## Reviewing with a second model

A reviewer on different weights is worth one thing: different blind spots. To get
that rather than noise:

- **State the invariant, not "review this."** "No path may drop a tag a human
  decided" produced most of the findings; "review this" produces style notes.
- **Inline the code it needs** — the changed function and its callers — instead of
  letting it read the repo. 10 KB of brief is seconds of prefill; a whole package
  is minutes, and the local servers run one task at a time.
- **Numbered questions and a line cap**, and require it to quote the exact line as
  proof or drop the finding. Roughly a third of what comes back is fabricated; the
  quote requirement is what filters it.
- **Two rounds.** Round two's job is "verify the fixes are complete and find what is
  still wrong." It has found a defect in the previous round's own fix — a default
  that guessed the destructive reading — which round one would have shipped.
- What it cannot see: interactions across files it was not given, and anything only
  running the program finds. A review pass never replaces executing the thing.

## Decisions already taken, not to relitigate

- **Standard library only, in Python.** A Go rewrite was proposed, costed and
  rejected: no build step and no dependency install are worth more than the speed,
  and the Unicode argument favours Python (Go's standard library has no charmap,
  norm or collate, and byte-slicing can split a character).
- **No new dependency for brotli.** Two feeds arrive brotli-compressed and stay
  flagged, not removed.
- `spam.jsonl` is a historical name: it holds every hand-curated removal, including
  superseded feeds and junk, and `triage.py` treats a line there as a human
  decision. Its label in the output is `hand:`, not `spam:`.
- `failCount` / `lastCheckTime` are gone on purpose. The old `check.py` tested
  `code >= 200 or code <= 299`, which is always true, so they measured nothing.

## Network etiquette

`harvest.py` is the only thing that talks to the internet, and it is polite by
construction: 8 lanes, **each host pinned to one lane** so a domain is never hit
twice at once, a pause between requests, and it resumes from `harvest.jsonl`
instead of re-fetching. A full pass over 2,454 feeds takes ~15 minutes. Do not
change that: the old script used 50 threads with no per-host serialization.
`harvest.py` never writes `feeds.json`.
