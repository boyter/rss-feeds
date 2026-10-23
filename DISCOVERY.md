# Finding more feeds

The bottleneck is **discovery**, not tooling. `add.py probe` + `merge` already
verifies and admits a candidate correctly; what is missing is a source of
candidates. This file records where they come from, what each channel was
measured to yield, and what not to waste a run on.

Everything here obeys the invariant: a candidate joins only after it has been
seen answering with a real feed. A list that *names* a feed is a lead, not an
addition.

## Where the list stands (2026-10-20)

2,454 feeds on 2,049 hosts. Two facts shape the plan:

- **Only 97 hosts carry more than one feed.** The list is one-feed-per-site, so
  category, tag and comment feeds on hosts we already trust are almost entirely
  uncollected.
- **The file is skewed.** `type:personal-blog` 1,419, `topic:software-engineering`
  575; but `region:` appears 361 times across 33 values and `language:` 33 times
  across 15. Non-English and non-US/UK feeds are the thinnest coverage we have.

## What the first run measured (2026-10-20)

Thirteen curated lists, the common-path expansion, and the sibling pass, run
through `discover.py` + `add.py probe` + `add.py merge`. **2,454 → 3,462 feeds,
2,049 → 2,515 hosts, nothing removed.** Reproduce at the bottom.

| channel | candidates | answered as a feed | merged |
|---|---|---|---|
| 5 curated lists (README) | 1,497 | 591 (40%) | 302 |
| same lists, after 8 more lists | 2,215 | 829 (37%) | 220 |
| bare homepages → common feed paths | 2,233 | 317 (14%) | 39 |
| **single-feed homepages → `altFeed` links** | **418** | **406 (97%)** | **348** |

The sibling pass is the best channel by a wide margin, and the cheapest: the
host is already vetted, the site's own HTML declares the URL, and 829 of the
1,459 links it found were feeds we already carried — which is the check that says
the channel is real rather than a parser artefact.

The 70% live rate from the earlier 30-URL pilot was optimistic: it sampled only
URLs that already looked like feed URLs. Over a whole curated list it is 37–40%,
and the lists are a decade old, so that is the honest number to plan on.

Still open: **one feed** sits in `data/DISCOVERY_UNTAGGED.md` —
`labs.cosmicbytez.ca`, whose title says nothing about what it publishes. A
guessed topic is pinned forever, so it stays queued rather than joined.

### Working the queue (same day)

The 650 queued feeds became 647 merged feeds and one held-back row: **2,454 →
4,109 feeds, 3,001 hosts** for the session. What it took:

- 576 drafted host rules, generated from the queue's curated category plus the
  feed's own title, then read and corrected: 40 RPG blogs misfiled as
  `topic:personal` moved to `topic:gaming`, 12 personal-blog guesses that are
  plainly publications corrected, and 6 aggregator keys (`youtube.com`,
  `medium.com`, the feedburners) widened to URL rules — a `youtube.com` host
  rule would have replaced the existing one and retyped ~30 feeds already in the
  list.
- Two rules in `discover.py`'s tag cascade were wrong in ways only the queue
  exposed: a **host rule's topics** were refused everywhere, which left 240
  feeds untagged whose only evidence was a human's own site rule, and **URL
  rules were never looked up at all**, which is why the last 116 rows stayed
  queued after their rules had been written.
- `decide.py` now refuses a rule that would retype feeds already in
  `feeds.json`, or that drops a tag the previous rule for the same key carried,
  unless `--allow-type-change` says the change is the decision. Batch three
  drafted `techcrunch.com ... type:personal-blog` and `feeds.npr.org ...
  type:personal-blog`; applied, those would have silently retyped three
  publications and NPR's podcast feeds. Nothing in `overrides.jsonl` was
  "replaced", so the old replacement report caught none of it.
- The pipeline caught one of the additions: `feeds.feedburner.com/TechCrunch`
  is a name-squat already recorded in `spam.jsonl`, and the drafted rule
  re-admitted it. `triage.py` removed it again and the rule was deleted.

A feed that is a *sibling* of one already on an aggregator host gets no topic
from its sibling, and a feed on an aggregator gets no topic from the host rule:
youtube.com, the feedburners, reddit.com and medium.com each name a different
publisher per path. That is `AGGREGATOR_HOSTS`, and it is pinned by tests on
both doors.

51 hand host rules were written for the batch (as a transient file of my own
naming, fed to `decide.py`), and `TAGS.md` gained `region:italy`, `mexico`, 
`pakistan`, `philippines`, `poland`, `ukraine` and `language:polish`,
`ukrainian`, `urdu` — the coverage the list was thinnest on.

What the run cost in defects, all of them now pinned by `tests/test_discover.py`
or `tests/test_pipeline.py`, and all found by a reviewer on different weights or
by a test written before the fix:

- A bare URL sharing a line with a markdown link was never yielded, so a lead
  reached no candidates file and no counter. 39 feeds were invisible.
- An OPML file written on one line parsed to nothing, which looked like an empty
  source rather than a broken parser. Now ElementTree, with a regex fallback for
  malformed OPML.
- A curated README linked its own `.opml` files. OPML is XML that parses, so
  `probe` recorded them as feeds. Non-feed paths and hosts are filtered before
  probing.
- Applying a **host rule's topics** to a new feed repeats the npr.org mistake in
  the other direction: `youtube.com` carries `topic:science`, which made
  Bon Appétit and Bloomberg Originals science channels. A host rule may settle
  `type:` only — the limit `merge_tags` already enforced, now enforced twice.
- The same failure arriving through a different door: inheriting a **sibling
  feed's** topic on an aggregator host, where every path is a different
  publisher. Found in review round two; the first test written for it did not
  reach the buggy line, and the mutation check caught that.
- `triage.py` deleted two live feeds. `blog.jetbrains.com/feed` answers **202**
  with an HTML interstitial to the harvester and clean RSS to `curl
  --compressed`; a 2xx that is not 200 now flags as `challenge:202` instead of
  falling through to `remove:not-a-feed`.
- `discover.py extract` first wrote to `data/candidates.jsonl`, which is
  committed and holds hand-proposed candidates with tags. It overwrote human
  decisions. Generated lists now go to `data/candidates.discovered.jsonl`.
- A batch of host rules silently replaced an existing rule for `github.blog`
  and dropped its `topic:security`. `decide.py` reports the replacement, which
  is the only reason it was noticed; the rule now carries both topics.

A tag taken from anything other than the feed itself is written out to
`data/DISCOVERY_REVIEW.md` before the merge, never absorbed silently.

## Channels, ranked by yield per fetch

### 1. Curated lists and OPML files on GitHub — start here

Verified present and fetchable without a token:

| source | new-host candidates | what it is good for |
|---|---|---|
| `plenaryapp/awesome-rss-feeds` README | 755 | general; **organised by category, so tags come free** |
| `muchdogesec/awesome_threat_intel_blogs` | 307 | `topic:security`, our second-strongest topic |
| `tuan3w/awesome-tech-rss` | 156 | tech, several non-English sections |
| `vishalshar/awesome_ML_AI_RSS_feed` | 49 | `topic:ai` |
| `shgysk8zer0/awesome-rss` | 47 | general |
| `spians/awesome-RSS-feeds` `countries/with_category/*.opml` | unmeasured | **per-country OPML — the fix for the `region:`/`language:` gap** |
| `paulirish/frontend-feeds` (OPML) | unmeasured | `topic:web-development` |

Two things to keep in mind. The lists are old: ~30% of what they name is dead,
which is exactly what `probe` is for. And a list's own category is a *hint*, not
a decision — `classify.py` rules and `decide.py` overrides still have to say so.

Search for more with the unauthenticated search API (10 req/min, 60 req/hr on
core — do not loop it):

```bash
curl -sS "https://api.github.com/search/repositories?q=awesome+rss&per_page=20"
curl -sS "https://api.github.com/search/repositories?q=opml+rss+feeds&per_page=20"
```

### 2. Sibling feeds on hosts already in the list — the best channel

`discover.py siblings` proposes the homepage of every host that contributes one
feed; `add.py probe` fetches it and `harvest.probe` records the page's feed links
in `altFeed` without calling the page a feed; `discover.py leads` turns those
links into candidates. 1,952 homepages named 1,459 feed links, 829 of which we
already carried, and 348 of the rest joined the list at a 97% live rate.

### 3. Link-graph expansion (needs a small code change)

1,419 personal blogs link to other personal blogs. Harvested item titles are
already in `harvest.jsonl`, but **item links are not** — `harvest.py` keeps six
titles and drops the `<link>`. Keeping item links (capped, as everything else is
capped) turns every good feed into a source of new domains, which then go through
common-path probing (`/feed/`, `/index.xml`, `/atom.xml`, `/feed.xml`,
`/rss.xml`, `/feed.json`). This is the only channel that keeps producing after
the curated lists are exhausted.

### 4. Platform conventions

Sites on a known engine expose a feed at a predictable path, and the engine is
often detectable from the HTML (`generator` meta, `X-Powered-By`, asset paths):

- Ghost → `/index.xml`; WordPress → `/feed/` and `/comments/feed/`; Hugo →
  `/index.xml` + `/categories/<term>/index.xml`; Jekyll → `/feed.xml`.
- Substack, Medium, GitHub (`/<user>/<repo>/releases.atom`), YouTube
  (`/feeds/videos.xml?channel_id=`), GitLab, Discourse (`/latest.rss`).

Useless without a source of domains, so it is a *second stage* for whatever
domain list channel 1 or 3 produces — not a channel of its own.

### 5. Blocked candidates already parked

`BLOCKED_CANDIDATES.md` lists 15 real publications that 401/403/429 the
harvester (Politico, Lawfare, Carbon Brief, El País, ACM Queue, …). They are
worth one browser check each, then a re-probe. Small yield, but they are
`type:publication` feeds, the facet we are thinnest on after personal blogs.

## Do not bother

- **Common Crawl CDX.** `url=github.io&matchType=domain&filter=mimetype:application/rss+xml`
  returned **HTTP 504 after 60 s** on 2026-10-20. Domain-wide CDX scans time out
  at this scale; the bulk index files would work but are a different project.
- **Search-engine scraping.** Rate-limited, ToS-hostile, and the results are the
  same sites the curated lists already name.
- **"Top 100 RSS feeds" pages.** The README of this repo exists because those
  pages are funnels to a subscription product; they name the feed but rarely
  print its URL.

## The tool

`tools/discover.py` turns a list that names feeds into candidates. It never
fetches a feed and never writes `feeds.json`:

```
discover.py fetch sources.txt   # the handful of list URLs, nothing else
discover.py extract             # -> data/candidates.discovered.jsonl
discover.py paths               # bare homepages -> common feed paths
discover.py siblings            # single-feed homepages, to find their siblings
discover.py leads               # altFeed links probe found on pages we trust
discover.py tag                 # tag from the feed's own title, hints as fallback
```

`tag` writes two reports a human has to read before merging:
`data/DISCOVERY_REVIEW.md` (tags taken from a heading, a host rule or a sibling)
and `data/DISCOVERY_UNTAGGED.md` (answered as a feed, no decidable tags — the fix
is a host rule via `decide.py`, one line per site).

## Batch workflow, per channel

1. `discover.py fetch data/sources.txt && discover.py extract` (then `paths`,
   `siblings` or `leads` as the channel needs).
2. `python3 tools/add.py probe data/candidates.jsonl` — resumable via
   `data/probe_results.jsonl`.
3. **Read the titles `probe` prints.** This is the human step and it is not
   optional: the title is how a wrong URL and a hijacked feed get caught.
4. `decide.py` for the host rules the batch establishes (one rule per host, not
   one per feed — 1,309 candidates on ~1,100 hosts).
5. `add.py merge`, read `feeds.json.new`, then `--apply`.
6. `classify.py && rebuild.py --write && cmp feeds.json feeds.json.new` — after
   a merge the diff is *not* expected to be empty, but every line of it must be
   explicable as a feed this batch added or a tag an override just settled.

Run the suite before and after: `python3 -m unittest discover -s tests`.

## Reproducing the run

```bash
python3 tools/discover.py fetch data/sources.txt
python3 tools/discover.py extract && python3 tools/discover.py paths
python3 tools/add.py probe data/candidates.discovered.jsonl
python3 tools/add.py probe data/candidates.paths.jsonl
python3 tools/discover.py tag          # read the two reports it writes
python3 tools/decide.py my-decisions.txt   # the batch file is yours to name
python3 tools/add.py merge data/candidates.tagged.jsonl   # then --apply
```

## Rounds three and four: what the channels were worth

| channel | offered | real | rate |
|---|---|---|---|
| links found on pages of already-trusted hosts (`leads`) | 556 | 524 | 94% |
| curated lists, second batch (security feeds, newsboat dumps, country OPML) | 1,978 | 214 | 11% |
| sibling feeds, widened to hosts carrying two feeds | 2,878 | 23 | 0.8% |

The sibling pass is finished: past one feed per host it stops paying. `leads` is
the channel worth running again — it costs nothing but a fetch of pages whose
host is already vetted. The newsboat dumps are mostly 403s and JS-walled pages;
they belong in `BLOCKED_CANDIDATES.md`, not in a probe queue.

## What the lists get wrong

`mrtouch93/awesome-security-feed` files National Review, the Washington
Examiner, The Oatmeal, Megatokyo, Draplin, swissmiss, Signal v. Noise and
Newsboat under security headings, and one of its categories is the literal
string `http://127.0.0.1/rss.xml me`. 29 rules were rewritten from the feed's
own title instead of the list's claim. A list's category is a lead about the
topic, never the topic.

Two feedburner aliases of techcrunch.com answer with a real feed titled "Crunch
Hype": the alias was squatted. Parsing is not admission; `spam.jsonl` took them.
So did `trustwave.com/en-us/rss/spiderlabs-blog/`, which the publisher itself
titles "[DO NOT USE]".

## decide.py's overwrite guard, and what it protects

A host rule that sets `type:` over a site publishing two kinds of feed cannot
preserve both — toucharcade.com has article feeds and a podcast feed, and the
rule retypes one whichever way it is written. decide.py now refuses such a rule
outright, and the rules for toucharcade, carscoops and jalopnik were deleted so
the per-feed tags already in feeds.json stand.

The guard compares against **HEAD**, not the working tree. It used to compare
against the working tree and then refused a correction of its own rules from ten
minutes earlier ("you would drop topic:security from the existing rule"), which
is how a guard becomes noise. The invariant protects decisions that have
shipped.

## The queue

4,762 feeds on 3,257 hosts. Six rows remain queued, three hosts held back
because their titles decide nothing (`labs.cosmicbytez.ca`, `colinwalker.blog`,
`lmika.org`) and their duplicates. A guessed topic is pinned forever, so an
undecidable title stays in the queue rather than getting a coin flip.

## Aiming at a gap: medicine, religion, military

`discover.py pages <sites>` asks a named site which feeds it has, instead of
guessing a path. It writes homepages only and never fetches; `add.py probe` does
the fetching and `leads` turns the answers into candidates.

The measurement, in order:

- 52 named feed URLs → 19 serve a real feed (37%). The 33 failures are mostly
  paths I invented: `/rss/bmj_recent.xml`, `/rss/all.xml`, `/feeds/rss/all`.
- Those 19 took `topic:medicine` to 3, `topic:religion` to 11, `topic:military`
  to 15.
- Asking the 28 sites that failed instead: 2 of 28 named a feed link in their
  HTML. One of the two was already in the list.

So the thin topics are thin for a reason. NEJM and The Lancet answer 410, BMJ
and Medscape and CDC 403, Jane's serves a JS app: the clinical and defence
press is behind the same fingerprinting that blocks schneier.com, and it does
not advertise feeds in the HTML we can read. Filling those topics means a
browser check per site, one at a time, which is a human afternoon rather than a
tool.

## Twelve feeds the product carries and cannot decide

They answer 403 (ahilado.wordpress.com, danielspost.news.blog,
developer.salesforce.com, hanszandbelt.wordpress.com, blowthetruth.com),
5xx (abramov.io 503, giftegwuenu.com 522, globalreport.news 522), or their TLS
is broken (programmingwithmosh.com serves a certificate for another host,
thevividreader.com times out mid-handshake). None has a title, so nothing
decides a topic, and a tag written into `feeds.json` is pinned forever.

They stay in the list — a 403 is not evidence a feed is dead — and they stay
untagged. `rebuild.py --strict` names them every run, which is the honest place
for an undecided thing: visible, not guessed.

Two of the fourteen that started this check were removed by hand, with the
evidence quoted in `REMOVED.md`: `quicktrendnews.wordpress.com` (the feed's own
title is its domain name, its description is "The news above control", and its
item headlines are rewritten junk) and `www.headlinesoftoday.com` (`/feed`
answers 404 with `{"error":"not_found","path":"/feed"}`).

## The oracle channel: ask a feed index about a host we already carry

`discover.py oracle` queries feedsearch.dev (`GET /api/v1/search?url=<host>`,
no key, no signup) for sites we already publish, and writes what it answers as
**leads**. Answers are cached in `data/oracle.jsonl`, so a re-run does not
re-ask, and `skip_crawl=true` by default: asking the index to crawl means a
third party fetching a stranger's site on our behalf.

Measured, first batch — 5 sites:

| site | named | live |
|---|---|---|
| bmj.com | 14 | 13 |
| breakingdefense.com | 7 | 3 |
| xkcd.com | 2 | 2 |
| www.schneier.com | **385** | **0** |

The index invents feeds. All 385 schneier.com leads were
`/blog/archives/2025/01/post.html/feed` — `/feed` appended to every page it
crawled — and none served anything. `FEED_UNDER_A_PAGE` now drops a feed path
hanging off an HTML page: 381 of those 410 claims. Deliberately html/htm only:
WordPress serves real feeds at `/index.php/feed/`, and cutting `.php` would have
deleted a live pattern to stop a dead one. Both cases pinned by tests.

Measured, second batch — a random sample of **40 of our 2,373 single-feed
hosts**: 26 of 40 have feeds we do not carry; 403 claims, 395 after filters;
**331 of 395 live (84%)**, 314 new to the list.

But those 314 sit on **16 hosts**, and one of them — `khabaronline.ir` — is 257
of them. The channel is a power law: 9 hosts gave one feed each, one gave 257.
Scaled naively over 2,373 hosts that is tens of thousands of lines, most of them
section feeds of a handful of publishers. So this channel needs a per-host cap
before it runs wide, and the cap is an editorial decision about what the list is
for, not a bug to fix.

What it is already good for, un-capped: the thin topics. This pass took
`topic:medicine` from 3 to 15 (The BMJ's section and podcast feeds, which
advertise themselves nowhere our harvester can read — the root `bmj.com/feed`
403s us) and `topic:military` to 16.

## Gentle oracle, and the pile-up arriving at the gate

`discover.py oracle` is throttled and capped, because the measured shape says it
must be: one query at a time with a `--pause` (default 1s) against someone else's
free service, answers cached, and `--max-leads-per-site` (default 6) applied
after dedup, keeping the **shallowest paths** — `/feed` and `/category/tech/feed`
before `/category/a/b/c/d/feed`. In the run below the cap dropped 3,049 of 3,422
claims.

A second life for the dead lists: 610 hosts appear in the lists we already have
and our harvester never read a feed from them. A random 150 of them:

- 94 have feeds the index knows; 3,422 claims → 329 leads after filters and cap
- **176 of 329 live (53%)**, 166 of them new to the list, on 53 hosts
- 31 merged, 140 left for a human

### The pile-up, caught before it merged

Of the 53 oracle leads the tagger first said were feed-backed, 15 were aggregator
hosts carrying two or more topics that came from **item headlines**:

- `feeds.feedburner.com/defense-news/land` → `topic:software-engineering`
- `feeds.a.dj.com/rss/RSSMarketsMain.xml` (WSJ Markets) → `topic:food`
- `rss.sciam.com/observations/feed` → `topic:mathematics`

`classify.haystack` is title + description + six recent headlines, and for a
candidate about to be pinned forever that last term is not evidence. cmd_tag now
takes **topics only from title and description**, capped at two, while type,
region and language still read the full haystack — a Cyrillic headline is
evidence of language in a way a headline is not evidence of topic. Two tests pin
both directions; each fails with the fix reverted, and one of them was vacuous
until it was made to require a tag as well as forbid the wrong one.

After the fix: 30 of the 53 tagged, none with more than two topics, WSJ Markets
`topic:finance` alone. The other 140 are queued rather than guessed.

## The seam: what a keyword-search source would have to provide

Everything below `probe` already works for a source that searches by topic
instead of by host. The pipeline does not care where a URL came from; it cares
that someone fetched it. So a search source is one function:

```
query("nursing", language=None, limit=50) -> [{"url": ..., "title": ...}]
```

plus three things it must not do:

- **it may not decide a tag.** A search index files a feed under a heading, and
  headings are the source's claim, not ours: the security list carried The
  Oatmeal and the Washington Examiner. Topics come from the feed's own name, or
  from a human.
- **it may not skip the probe.** Its index is a snapshot; feeds move, die and get
  name-squatted between its crawl and ours. `feeds.feedburner.com/TechCrunch`
  answering "Crunch Hype" is what a stale index looks like.
- **it may not be the only key.** Candidates enter deduplicated on
  `vocab.norm_key` and land in `data/candidates.*.jsonl` like any other channel,
  so a second source cannot add a line for a feed we already carry.

`discover.py oracle` is the working example of that shape: it queries a third
party, caches the answers, filters for plausibility, caps per publisher, and
still makes `add.py probe` decide. Swapping the per-host endpoint for a keyword
endpoint is the whole change.

## The directory that searches: rssamplifier.com

Found by the user. `robots.txt` and `skill.md` name the entry points and say
reading them is preferred to crawling the HTML: `/api/search?q=`,
`/api/feeds?limit=&offset=&kind=`, `/topics/{kw}.json`, and `/opml` — the whole
directory, 44 MB, or one subject with `/opml?topic=`. ~199k blog feeds, 311k
podcasts. `discover.py amp` uses the last one: a file of subjects in, leads out,
one subject at a time with a pause, answers cached in `data/amp.jsonl`.

Measured on 26 subjects the list is thin on (medicine, nursing, theology,
military, hindi, poland, africa, nigeria, pakistan, ukraine…):

- the directory named **8,731 feeds**; `--max-per-query 25` kept 617, deduped to 579
- **543 of 579 live (94%)**, 540 new to the list, on **380 hosts**
- the largest single contributor was `anchor.fm` with 90 — an aggregator, capped by
  the same rule as everywhere else

**543 live from 26 queries.** Nothing else measured this session is close: the
per-host oracle gave 84% but only ~15 leads per host, curated lists 11–40%, path
guessing 0.6%. This is the channel to run wide, subject by subject, because it is
the only one that reaches hosts we have never heard of.

What it did not do: close the topic gaps. `topic:medicine` is still 15, because a
subject heading is a hint and never a tag — the nursing and palliative-care
podcasts merged as `topic:health`/`topic:media`, which the feed's own name
supports. 311 directory leads are queued undecidably rather than tagged on the
directory's say-so.

## Running the whole directory through, in tranches

`discover.py amp --all` downloads `/opml` once (106 MB, **546,502 entries**,
cached under the gitignored `data/sources/`) and emits a bounded tranche:
`--max-per-host 2` and `--limit 1500`, ordered by host then url, skipping
anything already probed — so the next run resumes rather than repeats.

Two tranches measured here: 1,498 + 1,498 leads, **1,417 and 1,402 live (95%,
94%)**, 747 merged after tagging. 4,824 → 5,857 feeds, 4,143 hosts.

The whole-directory OPML carries **no categories** (1,498 of 1,498 rows have an
empty outline path), so the heading-as-hint path that curated lists use yields
nothing here. The binding constraint is tagging, not discovery: each tranche
produces ~1,400 verified feeds of which ~360 get tags a reader can defend from
the feed's own name, and ~1,080 sit queued. Discovery at this rate is a solved
problem; deciding what 1,000 feeds named "Bone to Pick Podcast" are about is not.

## Clearing the untagged queue by hand (2026-10-20)

The queue, not discovery, was the binding constraint: 1,059 verified-but-untagged
rows sat in `data/DISCOVERY_UNTAGGED.jsonl`. Every row was read against its own
title and description (never the channel's say-so) and decided as a URL rule
with `decide.py`. Delegation was tried first and failed four times: worker
subagents on the local 27B never got past generating the decision list (output
cap killed each attempt); reading 22 rows at a time inline, ~2 decisions/minute,
was the working mode.

| | |
|---|---|
| queue rows read | 1,059 of 1,059 |
| URL rules written (`decide.py`, one batch) | 798 |
| rows deliberately skipped (undecidable, hijacked, blank) | 261 |
| merged | 799 (798 + the one previously-tagged trustwave row) |
| removed by a standing hand decision | 1 (trustwave SpiderLabs, `[DO NOT USE]` in its own title, `spam.jsonl` decided it) |
| product | 6,228 → 7,026 feeds, 4,498 → 5,218 hosts, 6,710 titled |

Two defects this pass found, both pinned by tests:

- **`cmd_tag` dropped a URL rule's `region:`/`language:`.** decide.py had
  written `language:french` on ~800 rules; the tag step copied only topic and
  type onto the candidate, so the merge would have pinned feeds without the
  language their human decided. Fixed in `discover.cmd_tag` (the rule's facet
  tags outrank the keyword guess for the same facet); test
  `URLRuleFacetsReachTheCandidate` fails without the fix.
- **`decide.py` reads existing rules from HEAD** (landmine #7, hit for real):
  three separate `decide.py` runs each rebuilt `overrides.jsonl` from HEAD plus
  that batch, silently dropping the previous batch's 260 rules. The fix is
  procedural — one `decide.py` run carrying the whole session's decisions — and
  `git diff --stat` on overrides.jsonl (798 insertions, 0 deletions) is the
  check that proves it.

A hijack caught by reading titles, per the add.py rule: `feeds.feedburner.com`
alias `Crunch Hype` squatting the TechCrunch name with a digital-marketing-farm
description. Left in the queue, not merged.

## Tranche 4 (2026-10-20, later run)

`amp --all --limit 1500 --max-per-host 2`: 1,500 leads, **1,372 live (91%)**;
372 auto-tagged by existing host/URL rules and merged, 999 queued for reading.
6,228 → 7,397 feeds, 5,577 hosts. The oracle widening over never-asked
single-feed hosts was launched the same afternoon (see *Open work* in RESUME
for the re-derive command); its numbers land here when it completes.

## The per-host oracle run wide (2026-10-20)

Every never-asked single-feed host, one batch: **4,088 hosts asked, 19,039
feeds named by the index, 2,238 hosts it knows nothing about**, 12,872 leads
cut by the per-site cap of 6 (the cap carried its weight again), 400 dropped
by the feed-under-a-page filter. After probe: **3,664 live leads (84%, the
measured rate)**, of which **1,236 were taggable from existing human rules**
(475 host rule + host rule, 412 from the feed's own name, 345 one host rule)
and merged; **1,784 joined the human queue**. 7,397 → 8,632 feeds, 5,646 hosts.

The run lost 16 sites to HTTP 429 from the free index, and the cached error
row made the loss permanent - fixed in ccdc4cc (retry 30s/60s keyed on the
error *string*, since the query helper never raises; failed sites no longer
cache), so a re-run re-asks exactly those. Two things this channel is now
measured to be: excellent for **section and category feeds of hosts we
already vetted** (that is what the index knows and our rules can decide -
84% live, 34% auto-decidable), and exhausted for breadth: 55% of asked
single-feed hosts have no second feed at all.

## Working the 1,784-row human queue (2026-10-21)

The whole queue was read by hand, multi-host entries first (one host rule
covers a site: `feeds.crikey.com.au`, `nu.nl`, `techinasia.com` with pathTags
for the sections), then the ~950 single-host rows 22 at a time. Measured:

- 1,392 rows decided (≈78%); 392 deliberately skipped — blank or undecidable
  title+description, `Comments on:` feeds, stale mirrors, hijacked feedburner
  names (3 more spam.jsonl entries: `Crunch Hype` alias, `OpenWebPodcast`,
  plus a pirated-download farm and a personal feedbin export).
- Two settle rounds merged **+622 and +772 feeds: 8,632 → 10,024**, 6,421 hosts.
  Harvest resumed cleanly (771 fetches), 116 tests green, product idempotent.
- The retype guard earned its keep again: ~15 drafted host rules collided with
  feeds already shipped under a different type; each was aligned to the shipped
  type or demoted to per-feed URL rules. One mis-copied index was caught by
  grepping the batch file back against the rows — write decisions through the
  row index, never transcribed URLs.
- Next: the queue only refills from new discovery (amp tranche 5, or
  gap-directed amp for thin facets: medicine, mathematics, transport).

## Planets (2026-10-21)

PlanetSoftware aggregators publish member feeds right in their index HTML.
Ten planet indexes appended to `sources.txt` (debian gnome freedesktop kde
gnu wordpress openstreetmap ubuntu mozilla planetpython; eclipse/libreoffice
unreachable, wikimedia moved to a wiki page). **9 serve their own aggregate
feed and joined as `type:aggregator`** (OSM's /rss feeds are data-dump
notices, not articles; planet.ubuntu.com serves `/feed`, not `rss20.xml`).

Members: the index hrefs were mined with the FEEDISH path filter (557
unique member-feed leads -> `data/candidates.planets.jsonl`), probed at a
**64% live rate (359 feeds)**. Members of a vetted planet are human-curated
by the planet operators, so they are the highest-quality leads the project
has after the sibling pass. Two traps:

- Do **not** let the planet pages through `extract`: their item bodies
  contain every URL the members cite (one 967 KB page = tens of thousands
  of leads). The page files live in `data/sources/planets/`, which extract
  skips, and are mined with the targeted href pass instead.
- `cmd_tag` ignores tags already present on a candidate row - hand-tagged
  files merge directly with `add.py merge`, they do not round-trip `tag`.

## Planet members (2026-10-21, continued)

The 308 live-enough member rows were read in 14 sittings: 244 decisions
(nearly all host rules - a planet member is one author, and their tag/subsite
feeds all inherit), ~64 deliberate skips (LiveJournal personal pages, dead
GSoC archives, blank blogs). **239 merged: 10,595 → 10,834 feeds, 6,691
hosts.** The channel is measured: 10 planets live -> 9 aggregate feeds + 557
member leads + 64% probe rate + 79% decidable-by-reading.

The pass exposed a precedence defect in `discover.cmd_tag`: a list heading's
type (or any rule-engine guess) was consulted **before** a human's host rule,
so reproducible-builds.org reached the candidate file as `type:vendor-blog`
while the human rule said `type:institution`. merge_tags has always said a
hand decision excludes the rules for the facets it speaks to - cmd_tag was a
second, disagreeing copy of that law. Fixed in 9d0f8b0 with two pinned tests
(host rule beats the heading; a URL rule still beats the host rule), each
mutation-verified in both directions.

## Queue part 2: the amp/rssamplifier survivors (2026-10-21)

3,031 rows left after the first queue pass, ~96% single-host. Processed in 12
batches. Rows 0-191 read by hand inline; rows 192-3030 (2,839) delegated to
same-model subagents with a compact rulebook (/tmp-style, two files only: the
rulebook + a numbered dump of exactly that batch), each batch returned through
`decide.py` here — the gate caught what the rulebook could not: invented
vocabulary (blocked), host keys written with a scheme (134 lines, fixed by
stripping), and two retype collisions (trustedsec, affirminggender - demoted
to URL rules matching the shipped type). One reported SPAM line turned out
never to have been written to disk: the human file was checked and the entry
added by hand, never trusted from a report.

Measured: ~1,830 rules written, 2,393 candidates merged, **10,834 -> 13,223
feeds, 8,835 hosts**. Skips ran ~20-25% of rows (blank Substack boilerplate,
unknown-person microblogs, comments feeds). 4 removals all hand-verified:
`abnormalreturns.com` was a FALSE not-a-feed (curl proves a real RSS body;
`harvest.py --retry-failed` rescued it) - the other three (dead DNS, 404 x2)
confirmed in a browser-equivalent fetch before merge of the removal.

## Medicine tranche via the amp directory (2026-10-21)

`GitRSS` turned out to be a plan item with no referent: gitrss.com (and .io/.dev/.net,
and gitrss.bradeon.com.au) are NXDOMAIN at the TLD root and have zero Wayback
snapshots. Unrecorded channels cost a detour; record channels when you measure them.

Substituted `discover.py amp` with 12 medicine/health subjects: 495 candidates,
406 live (82%), 335 rules through two delegated batches (medicine-vs-health split
per the brief), 288 merged: **13,223 -> 13,509 feeds; topic:medicine 65 -> 175**.
Two hand-verified spam removals (NYT-lookalike scraper, market-report mill).

`add.py merge` now refuses candidates the harvest last saw dead, even when the
probe snapshot says alive: actuprepa and addisababamajlis re-entered from stale
candidates and were deleted again by rebuild - the trustwave loop replayed for
non-banned feeds. Pinned by TestMergeRefusesDeadHarvestEvidence (mutation-checked).

## Tranche 5 + gap queries + sibling re-pass (2026-10-22)

Three wells in one stretch, 13,509 -> **15,541 feeds, 10,381 hosts**:

- gap-directed amp queries (transport/economics/philosophy/journalism/military/
  networking/hardware/government...): 618 named, 542 live (88%), 434 rules.
  The thin facets moved: transport and government visibly up.
- amp tranche 5: 1,498 leads, 1,362 live (91%), ~1,160 rules in 6 delegated
  batches (batch 6 was 13 tail rows, done inline).
- sibling re-pass over the grown host list: 8,525 single-feed homepages probed,
  5,293 declare feed links, 540 new after dropping 6,409 already carried,
  482 live (89%), **439 auto-tagged by existing host rules** - zero new human
  decisions needed. The host-rule investment pays out here.

Removals this stretch, all evidence-backed: luigifreitas.me (personal site now
redirects to a casino affiliate - sold/hijacked) and alternativestheatrales.be
(valid RSS, but all six items are Italian casino spam: compromised site - the
item-counting rule caught what a title check and a curl of the feed head both
passed). altavoz.pe was a harvester false-negative, rescued by --retry-failed,
same as abnormalreturns before it. Two false negatives in one day says
remove:always-hand-verify is still earning its keep.

Delegation protocol held across 8 more batches: rulebook + one numbered batch
file, output gated by decide.py, /tmp/repair.py loop for retype/drop collisions
(auto facet-merge, align shipped types). Two rulebook gaps surfaced: `region:norway`
and `topic:culture` do not exist - the vocab gate catches them, the rulebook
should list the facet values verbatim.

## Queue pt3 (second pass with item evidence) + tranche 6 (2026-10-22)

The 1,028 queue rows every earlier pass skipped, re-dumped WITH up to four of
each feed's own item titles from the harvest. A fresh delegate pass over richer
evidence decided ~720 of them - a skip is not a verdict when the evidence grew.
Still skipped (~500): blank everywhere, comment feeds, placeholders. Those stay
queued; guessing an undecidable title is pinned forever.

Tranche 6 of the directory: 1,498 leads, 1,363 live (91%), ~1,260 rules in six
delegated batches. Together: **15,541 -> 17,417 feeds, 12,100 hosts**.

Spam this stretch (~12, each with quoted evidence in spam.jsonl): SEO
linkbuilding and bought-followers services, price-list and biography farms,
cracked-APK mills, gambling affiliates, and the feedburner name-squatters
(TechCrunch aliases) - the last now refused at `add.py merge` by the spam gate,
not after re-entry.

Rulebook lesson: its topic list must be verbatim from TAGS.md. Half-listed
vocabularies invent near-misses (`topic:tech`, `region:new-zeeland`,
"no hardware topic" when hardware exists); the decide.py gate catches every one,
but each catch is a wasted pass. The rulebook now carries all 45 topics verbatim.

## Tranche 7 + sibling leads #2 (2026-10-23)

Tranche 7: 1,499 leads, 1,386 live (93%), ~1,270 rules in six delegated batches.
Sibling leads #2 over the 12k-host list: 606 new links after dropping 1,600
comment feeds and the already-carried, 531 live (88%), all but 12 auto-tagged
from host rules; the 12 done inline. **17,417 -> 19,268 feeds, 13,183 hosts.**

The alternativestheatrales ping-pong, finally closed properly: it answered with
valid RSS (isFeed=true) so the dead-evidence merge gate waved it in, while
triage removed it for 6/6 casino items - so every settle re-added it and every
rebuild deleted it. A human entry in spam.jsonl is the only gate that stops a
hijacked-but-valid feed; added after a third hand-check (Zimbabwe betting +
Woospin under a theatre title). Lesson: feeds removed by *pattern* rules need a
spam.jsonl entry too, or the two honest writers keep disagreeing forever.
