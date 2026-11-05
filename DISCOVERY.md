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

## Tranche 8 (2026-10-23)

1,499 leads, 1,250 live (83%), 1,174 rules in five delegated batches:
**19,268 -> 20,471 feeds, 14,092 hosts.**

Removals hand-verified: asdr.gov.uz (HTML page), azh/blog feed 404 (Andy
Hertz's blog moved), designernews atom (serves HTML). arts.uoi.gr rescued by
--retry-failed - third harvester false-negative on a Greek/UTF-8 site.

Delegation drift this stretch: the w5 batch wrote 196 per-URL keys WITHOUT the
scheme; the guard caught every one, and the batch file made the repair
mechanical (match the key against the batch's real URLs - two turned out to
have different paths than the delegate remembered: index.xml vs rss.xml).
Rulebook note added: topic:programming:LANG is valid and should be used when
the feed is about one named language.

## Tranche 9 + topic:astrology added (2026-10-27)

1,500 leads, 1,395 live (93%), ~1,250 rules in five delegated batches:
**20471 -> 21818 feeds, 15,147 hosts, zero hand-verified removals** - the
cleanest settle yet (no dead feeds among the additions at all).

Vocabulary change, same-change rule honoured (TAGS.md + rules together):
`topic:astrology` added. The delegates kept skipping it - 17 rows in one batch,
plus stragglers in earlier ones - "no topic fits" is a vocabulary gap when the
cluster keeps recurring, not a judgment failure. 15 astrology feeds tagged;
the esoteric-but-categorizable line is drawn at actual astrology, not at
religion-adjacent wellness.

## Tranche 10 (2026-10-27)

1,498 leads, 1,313 live (88%), ~1,200 rules in four delegated 330-row batches:
**21818 -> 23076 feeds, 16,079 hosts.** Second consecutive zero-removal settle.
Spam refused before entry (6): SEO/gambling copy farms, a casino-hijacked
Iranian news feed, a book-promo link mill, and `balzaromagazine.co.uk` - the
delegate flagged it as a maybe-farm and asked for a human check; curl showed
all items are B2B SEO listicles ("Sweatshirts for Clubs", "GEO agencies")
under a magazine name. Delegates flagging borderline calls for verification,
rather than silently tagging or spaming, is the behaviour that keeps both
false removals and farm-tags out.

## Tranche 11 (2026-10-27)

1,498 leads, 1,369 live (91%), ~1,250 rules in four batches:
**23076 -> 24394 feeds, 17,101 hosts.** Third consecutive zero-removal settle;
9 spam refused at merge (crypto-shill podcast, "natural cure for cancer"
Substack, cam-site affiliate farm, casino-hijacked sites in Bolivia/Cameroon).

Process incident, recorded because it is a landmine in the ORCHESTRATOR, not
the delegate: `python3 tools/decide.py file | head -1` exits with head's
status, so a REJECTED batch looked like it passed and the settle chain
continued without those rules. Caught because the second `discover.py tag`
count came back oddly small; fixed the rule, re-applied, merged the remaining
224. Shell chains over decide.py must check for REJECTED, not exit codes.

## Tranche 12 + two spam-rule false removals caught (2026-10-27)

1,500 leads, 1,365 live (91%), ~1,230 rules in four batches:
**24394 -> 25507 feeds, 18,054 hosts.**

The near-misses matter more than the adds this time. Triage proposed
`remove:spam` on two feeds that hand-reading showed were real:
- `biblialiturgia.com` - "semana XXX del Tiempo Ordinario" x5: the Catholic
  lectionary's week 30 in ROMAN NUMERALS, matched as the adult token "xxx".
  The pattern is now case-sensitive for "xxx" (spam houses write it lowercase;
  Rome writes it uppercase).
- `benuyama.com/.../quit-porn-with-ben-uyama` - a genuine recovery podcast
  whose NAME names the thing it helps you quit. Adult-industry words
  (porn/xxx/onlyfans) can no longer fire on feed name alone; they count only
  via items at the >=3 threshold, like every other word. Casino/viagra words
  still fire on name - alternativestheatrales-style hijacks stay caught, and
  its item set is a pinned test.

Four new tests, mutation-verified: with the fix reverted exactly those two
tests fail. Rule: reading the ITEMS before applying a remove is not optional
ritual - it is where a counting rule meets natural language and finds the
Roman numerals.

## Tranche 13 (2026-10-27)

1,496 leads, 1,375 live (92%), ~1,270 rules in four batches:
**25507 -> 26821 feeds, 19,103 hosts** (blisty.cz rescued: harvest recorded
dead-domain, but DNS resolves and curl returns 41 KB of RSS - transient
resolver failure at fetch time, --retry-failed fixed it; the hand-check
before applying a remove caught the fourth harvester false-negative).
Delegate reply lost on batch 3 with the WORK complete (progressive writes):
coverage arithmetic (326 of 345, 19 uncovered ≈ the skip rate) said apply
it, no re-dispatch. blockchainmagazine.com spam hand-confirmed (BC.Game,
BiggerZ, 1win press releases); sister PR sites flagged for a future sweep.

## Tranche 14 (2026-10-28, settled 2026-10-31)

1,494 whole-directory leads, 1,333 live (89%), 1,206 rules written in four
batches (295/337/324/272), net **1,189** after 17 in-batch corrections:
**26,821 -> 28,071 feeds, 20,101 hosts** (27,708 titled). Zero-removal settle;
`REMOVED.md` untouched at its single macsparky line.

Merge refusals, 20 of 1,270 tagged rows, and they split in a way worth
measuring: **16 were `banned by spam.jsonl`** — the directory re-serves feeds a
human already removed, five `api2.wondercraft.ai/feeds/podcasts/*` press-release
syndication rows, `bitcoincasinosnews`, `nytimespost` (NYT-branded scraper),
`alltotalnews`, `articleify`, `balzaromagazine`, `alternativestheatrales`
(casino-hijacked), `beljanski` (cancer-cure promo), a crypto-shill podomatic
feed, a lepodcast placeholder, and the superseded Trustwave SpiderLabs feed.
A directory channel does not decay: expect banned rows in every tranche, and
`add.py`'s spam gate is what keeps them out. The other **4 are parked, not
refused**: probed live, but `harvest.jsonl` is newer and says dead (404
`actuprepa.substack.com`, 404 `aquilaos.com/feed.xml`, 200-not-a-feed
`addisababamajlis.org.et`, 200-not-a-feed `asdr.gov.uz`). They are tagged and
waiting for a `--retry-failed` pass; blisty.cz is the reason not to write them
off on a 200.

### The settle was not done at `add.py merge --apply`

`rebuild.py --write` after the merge differed from the product in **303 rows**.
Two causes, one benign and one not:

- Benign: `add.py merge` writes a candidate's own tags; the host-rule layer
  (`region:`, `language:`, pathTags) lands only in `rebuild.py`, which is the
  writer. 241 new rows and 62 pre-existing rows gained 403 rule tags, and the
  second pass is byte-identical, so it converges. **A settle is not complete
  until `rebuild.py --apply` makes `feeds.json` == `feeds.json.new`.**
- Not benign: three URL rules written in this tranche's batches destroyed tags
  an older rule had given the same feed - `topic:security` +
  `topic:software-engineering` collapsed to `topic:personal` on
  `blog.adambell.ca`; `topic:programming:javascript` + `topic:web-development`
  dropped from Mark's Dev Blog; `topic:data` + `topic:software-engineering`
  collapsed to `topic:programming` on `blog.joda.org`. `decide.py`'s guard
  compares the **same key**, so a URL rule that undercuts an older **host** rule
  walks straight through. Corrected additively (1b735d2) with `decide.py`, and
  the file diff proved it: 3 insertions, 3 deletions, 20,368 lines in and out.
  One drop survives and is defensible: the Jay Fields Blogger `?alt=rss`
  variant loses a stale `topic:books` to its host rule's
  `topic:software-engineering`.

Rule for next time: after a merge, read the `override replaced N tag(s)` lines
in `rebuild.py --write` output before `--apply`. That line is where a
this-session rule meets a shipped one, and it is the only place the destruction
is visible.

## Queue pass: the 1,037-row residue, read to the bottom (2026-10-31)

`data/DISCOVERY_UNTAGGED.jsonl` had grown to 1,037 rows. All of it was read
(title + description, ~150 rows at a time). Composition, measured before reading:
685 rows carried a description worth reading, 348 were name-only or blank
(title == description, or Substack's default "My personal Substack"), 4 were
`Comments on:` comment feeds. The last three groups stay in the queue: an
undecidable title is not a guess waiting to be made.

Wrote **294 URL rules** (one `decide.py` batch, committed before anything else):
`discover.py tag` then produced 314 tagged candidates and shrank the queue
1,037 -> **743**. `add.py merge` took **283**, refused **31**: 27 `banned by
spam.jsonl`, 4 parked as dead in `harvest.jsonl`. Product:
**28,071 -> 28,354 feeds, 20,260 hosts**, 27,991 titled, zero removals, 12
known untagged rows unchanged, `rebuild.py --apply` needed 6 tags from the
host-rule layer and the second pass was byte-identical. 132 tests pass.

**11 of my 294 rules were for feeds already banned in `spam.jsonl`.** That is
the lesson of the pass: a queue row can be perfectly taggable from its own name
and description and still be a farm, because the thing that made it a farm is
its ITEMS, which the queue row does not carry. `importpython.com` (Python name,
SEO listicle items), `avstarnews`, `bageltechnews`, `birminghamjournal.co.uk`,
`bartenders.com.bo`, `batchenga.cm`, `beenews.com.br`, `androidoyun.club`,
`aihausanovels.com.ng`, `anthroholic.com`, `bahardaily.ir` all read fine and are
all banned on their content. The merge-time spam gate is what makes
description-only tagging safe; without it this pass would have pinned 11 farms.

Channel yield: **283 feeds from 1,037 rows read (27%)**, at ~1 hour of reading.
The amp directory gives ~370 per 30 minutes with far less reading, because the
heading or the site tells you the subject. The residue is residue for a reason:
of the 743 rows left, ~500 are name-only/blank/comment feeds. Do not plan
volume around this queue; plan it around the directory and use the queue when a
pass is already running.

Vocabulary gaps this pass hit and deliberately did not paper over - rows left
untagged because no honest tag exists: animals and pet/animal-rescue sites
(dog rescue, horse sleigh rides, a reptile goods shop), linguistics and
language-and-naming shows, true crime, adult/erotic publishing. Four recurring
clusters, ~20 rows between them: if a future tranche hits them again, add the
tag to TAGS.md in the same change rather than stretching `topic:personal` or
`topic:entertainment` over them.

## Tranche 15 (2026-11-02)

`amp --all --limit 1500 --max-per-host 2`: 1,500 candidates, all probed
(probe_results 47,741 -> 49,241). `discover.py tag` produced **1,385 tagged**
candidates from **1,187 decisions** written in one `decide.py` batch
(1,186 in `decisions-t15b.txt` + 1 pin, below): overrides.jsonl
20,662 -> 21,849 (35 host rules, 1,152 URL rules added).

`add.py merge` took **1,354** at merge time, refused **32**: 27 `banned by
spam.jsonl` — the directory re-offers the farms every tranche, this batch
included five `api2.wondercraft.ai` podcast spams — and 5: the four known
parked deads (`actuprepa`/`aquilaos` 404, `addisababamajlis`/`asdr.gov.uz`
200-but-not-a-feed) plus `blog.nationalarchives.gov.uk/rss/news.xml`, which
answered 405 on **both** post-merge harvests and was dropped by the rebuild
before it ever shipped. It is a removal that never touched the product, so it
is recorded here, not in REMOVED.md.

Post-merge harvest fetched all 1,354: 1,352 `isFeed=true`, 1 timeout (flagged,
kept), the 405 above. `rebuild.py --apply` then layered rule tags; against
HEAD the product is **+1,353 added, 1 removed, zero shipped rows changed** —
every change is additive (region/language/one topic).

**The one pin.** `api.afripods.com` is a Kenyan podcast host and its first
tranche row, *Iko Nini Podcast* (Kenyan true crime), was about to pick up
`topic:programming` from a headline keyword — the documented rule-volatility
trap, caught because the pre-apply diff showed one **pre-existing** row
changing. Pinned with a URL rule (`topic:media type:podcast`, its shipped
tags), which excludes the headline rules for those facets. Lesson: after a
big rule batch, check the pre-apply diff for changed **old** rows, not just
the new ones; the new rows are expected to move.

**One shipped removal.** `blog.bitsrc.io/feed` (in HEAD) now 30x-redirects to
`bit.cloud/blog`, and `bit.cloud` serves HTML at every guessed feed path —
hand-checked with curl, no feed exists there. The publisher still publishes on
Medium: `https://medium.com/feed/bitsrc` is live (43 KB RSS), and the tagged
variant `medium.com/feed/bitsrc/tagged/web-development` is already in the
list. Re-pointing the line is a human decision; it is parked, and the old line
is recorded in REMOVED.md. Do not re-add the old URL.

Product: **28,354 -> 29,706 feeds, 20,260 -> 21,457 hosts**, 27,991 -> 29,340
titled. Second classify + `rebuild --write` byte-identical (fixed point),
132 tests pass. Untagged queue 743 -> 765. The 12 known untagged rows and the
6 standing type conflicts are unchanged.

## Tranche 16 (2026-11-03)

`amp --all --limit 1500 --max-per-host 2`: 1,498 candidates (probe_results
49,241 -> 50,739), 1,361 live. `discover.py tag`: 356 from sibling/host-rule
generalization of tranche-15 rules, 1,791 needing a human (1,026 new).

Read all 1,026 new rows (~8 batches) and wrote **711 URL rules** in one
`decide.py` batch, plus **15 pile-up pins** (below): overrides.jsonl
21,849 -> 22,575, all insertions. `add.py merge` took **1,035**, refused
**32**: the same 27 `banned by spam.jsonl` re-offers as tranche 15 and the
same 5 known deads (four parked + nationalarchives, 405 on every attempt).
Post-merge harvest: all 1,035 fetched, all live. **Zero removals.**

**Two tags added to TAGS.md** — the clusters hit three-plus times, per the
standing rule: `topic:legal` (Law Talk, Maurer School of Law, Bonatti Penal,
Borderlines) and `topic:animals` (Woodland Park Zoo, Bodega Cats of New York,
Au Bonheur des Bêtes, boriquagato — animal-rescue was the named gap). True
crime hit once (Blutrausch) and adult content three times (boardroomtobedroom,
Blonde Sunrise, Between the Sheets); both stay in the queue — one is not a
cluster, and adding an adult tag is a policy call, not mine to make.

**The pile-up, measured for the first time.** Of the 1,035 new rows, **84
gained 1–4 headline-rule topics at rebuild** that no human decided — most on
shared podcast hosts (libsyn, podbean, substack) where the only tag source is
a sibling generalization, so the feed has no URL rule of its own and the
headline rules are not excluded for the topic facet. This is the documented
failure mode, and it shipped the same way in tranche 15 (the 3speak rows in
HEAD already carry piled topics), but the rate is now visible: ~8% of a
tranche. Pinned the 15 rows whose titles make the noise obvious (bedtime
books + topic:ai, a Star Wars podcast + topic:business, Bogleheads +
topic:tech-industry, four 4-topic pile-ups). The 15 pins replace exactly the
sibling topic they displace, reported by `rebuild --write` as designed.
Countermeasure for a tooling pass, if the rate stays: when a candidate's tags
came from a sibling generalization (tagOrigin says so), treat them as the
decision that excludes headline topic rules — the data to do it exists.

Product: **29,706 -> 30,741 feeds, 21,457 -> 22,326 hosts**, 29,340 -> 30,373
titled. Against HEAD: +1,035, 0 removed, **zero shipped rows changed**.
Fixed point byte-identical, 132 tests pass. Untagged queue 1,791 -> 1,080.

## Tranche 17 (2026-11-03)

`amp --all --limit 1500 --max-per-host 2`: 1,500 candidates (probe_results
50,739 -> 52,239), 1,390 live. `discover.py tag`: 447 tagged (367 from
sibling/host-rule generalization of this tranche's own rules + 80 from a list
heading), 964 new untagged rows.

Read all 964 rows (~7 batches) and wrote **765 URL rules** in one `decide.py`
batch, plus **15 pile-up pins** (below): overrides.jsonl 22,575 -> 23,355.
`add.py merge` took **1,180**, refused **32**: the same 27 `banned by
spam.jsonl` re-offers and the same 5 known deads as tranches 15-16. Post-merge
harvest: all 1,180 fetched, all live. **Zero removals.**

**One tag added to TAGS.md** — `topic:comics` (comics, webcomics, manga,
graphic novels): six hits in this tranche alone (Webcomics Handbook,
Breadfinder, Brett Bean, Broken English, Broken Heart Studio, Brood), well
over the 3+ cluster rule. `topic:adult` candidates did not appear this pass;
the three queued rows from tranche 16 remain an owner decision.

**The pile-up again, slightly worse.** Of the 1,180 new rows, **118 gained 1-4
headline-rule topics at rebuild** (~10%, vs ~8% in tranche 16) — the same
shared-host pattern (libsyn, podbean, substack rows where the only tag source
is sibling generalization). Pinned the 15 rows whose titles make the noise
obvious (golf podcast + topic:ai, ministries podcast + topic:ai, real-estate
podcast + topic:sport, Outlook 4-topic pile-up, ...). Each pin is a URL rule
carrying exactly the topics the feed should have, so the rebuild report shows
the displaced topics as designed. The remaining ~103 rows carry piled topics
until the structural fix lands (see tranche 16): when a candidate's tags came
from a sibling generalization (tagOrigin says so), treat them as the decision
that excludes headline topic rules.

One tooling scare, resolved: mid-tranche the working-tree overrides.jsonl
kept snapping back to its committed state within seconds, silently dropping
the 765-rule batch between steps. No local process was found doing it
(watcher + trap logs); the countermeasure was to commit the batch the moment
it was verified, so any further restore became a no-op. If it happens again,
commit early and verify counts before every rebuild.

Product: **30,741 -> 31,921 feeds, 22,326 -> 23,239 hosts**, 30,373 -> 31,553
titled. Against pre-tranche HEAD: +1,180, 0 removed, **zero shipped rows
changed** (the 160 adjusted rows are all new rows gaining region:/language:
or the pinned corrections). Fixed point byte-identical, 132 tests pass.
Untagged queue 1,791 -> 1,279.

## Structural pile-up fix (2026-11-04, commit d342fac)

A tooling pass, not a settle. No feeds added, removed, or re-tagged: the fixed
point is **byte-identical** (`classify && rebuild --write && cmp`).

**The bug.** `merge_tags` excludes the rules' topics only when a *hand decision*
(override) speaks to the topic facet. A sibling-generalized feed — one whose topic
came from the candidate's own tags, written into `feeds.json` by `add.py merge`,
with **no URL override of its own** — never hits that exclusion. So the headline
keyword rules (matched over 6 item titles) lay a second topic on a feed that
already had one: a golf podcast gaining `topic:ai` because an episode mentioned
AI. Measured at ~8–10% of new rows per tranche (tranches 15–17), ~15 title-obvious
pins per tranche by hand.

**The fix.** In `merge_tags` (the single source of tag precedence, shared by
`classify.py` and `rebuild.py`): when `keep` already carries a `topic:`, drop the
`topic:` tags from `suggested`. A feed that already has a topic has a *decided*
topic facet — set by a hand decision, a sibling generalization, or the feed's own
name and description — and the rules read headlines, which is not a decision.
Rules still bootstrap a feed with **no** topic, and the filter touches topics
only (`region:`/`language:`/`type:` pass through). This is the per-tranche pinning
automated, and it subsumes it: no more pins needed going forward.

**Why byte-identical, and why.** At a fixed point every topic the rules would
add is already in `keep` (a prior rebuild wrote it), so filtering `suggested`
changes nothing for the shipped product. The fix only stops the *next* rebuild
(from a re-harvest, or a new merged feed) from piling. That is the proof it is a
tooling change, not a data change.

**Tests.** 132 -> 135. The old `test_a_type_only_override_does_not_strip_topics`
mis-wrote its own comment (it asserted a headline topic *piles onto* a feed that
already had a topic — the bug, pinned as a feature). Split into three: a
type-only override does not strip a decided topic; rules still bootstrap a
no-topic feed; and two new pile-up tests that **fail without the guard** (the
bootstrap test passes both ways, so the guard is what the pile-up tests turn on).

**Not retro-cleaned.** The fix filters what would be *added*, not what is
already in `keep`. The existing pile remains: **~1,976 rows (6.2%), ~2,953
noise topic instances**, by the precise signature (a topic a rule fires for on
the headlines but not on the feed's own name/description, and that no override
covers). Upper bound — feeds in other languages are false positives (Gitarrenkram
is correctly `topic:music`; the English rule did not fire on the German name).
A mechanical removal is not safe: `feeds.json` has no per-tag provenance, and the
invariant needs an explicit human decision to drop a tag. Left frozen (owner
decision on a bounded judgment cleanup pass is open).

## Pile-up retro-clean (2026-11-04, after the structural fix)

A data change, decided by the owner. Removes the accumulated pile-up the
structural fix (d342fac) only froze. **1,176 feeds, 1,481 topics removed.**
No feed removed, no title/type/region/language changed, no feed left without a
topic.

**The removal set** (per feed, from `draft.jsonl` — the same ground truth
`rebuild.py` applies): a topic is removed only if it (a) is a rule topic that
fires on the full haystack (title+desc+6 headlines), (b) does **not** fire on
the feed's own name/description alone, and (c) is **not** in the feed's `final`
override — i.e. it is specifically a headline pile-up, not a decided tag and not
an identity-supported tag. The guard: a feed is touched only if it keeps at
least one topic (its anchor). That means never a decided tag, never a tag the
feed's own name supports, never a non-firing (sibling) tag, never a feed's last
topic.

**Skipped (left frozen):** non-ASCII-name feeds (~199, foreign languages —
English keyword rules can't validate them; a German "Musikproduktion" podcast is
correctly `topic:music`) and no-anchor feeds (~231, every topic piled, so there
is no decided/identity topic to keep — a guess either way).

**Honest cost.** Sampled 60 ASCII feeds: ~85% are clearly correct, ~15% removed
a topic that is arguably the feed's real subject but only matched via a headline
because the name is cryptic/abbreviated — `SingularityHub` lost `topic:ai` (kept
`science`), `SEI Blog` lost `topic:programming`, `Body Bites` lost `topic:health`.
In every case the feed keeps an anchor and the change is one line in git
history (restore = re-add the tag). The net is strictly less noise; the residual
is a missing relevant tag on a small set, not a corrupted feed.

**Proof.** The cleaned `feeds.json` is a stable fixed point: `classify &&
rebuild --write && cmp` is byte-identical, so the removals do not come back under
the fixed rule, and the write matches the pipeline format exactly. 135 tests
pass. Diff of all 1,176 lines saved at `/tmp/pileup-cleanup.diff`.

## Tranche 18: the per-host oracle run wide for the first time (2026-11-04)

The oracle channel had only ever been run on hand-picked site lists. This asked
**500 never-asked single-feed hosts** — strided every 33rd through the sorted
list of 16,706, so the yield is honest for extrapolation rather than
alphabetical-first.

| | |
|---|---|
| hosts asked | 500 (index knew none for **398**, 80%) |
| index claims | 307 feeds on 102 hosts |
| filters | comment feed 45, duplicate in batch 8, feed under a page 1, per-site cap 95 |
| leads written | 158 |
| probed, answered as a feed | **143 (91%)** |
| already in the product | **93 of the 143** (78 by URL, 15 by `norm_key` — mostly `www.` variants) |
| genuinely new | 50 → **30 added**, 10 left in the untagged queue, 10 skipped |
| hand decisions | 21 URL rules in `overrides.jsonl` (23,355 → 23,376) |
| product | **31,921 → 31,951 feeds** (23,325 → 23,329 hosts, 31,553 → 31,583 titled), zero removals, zero pre-existing rows changed |
| harvest | 34,710 → 34,740 records; all 30 new rows recorded `isFeed=true` |

**What this channel is, measured.** It is *repair*, not volume: 65% of what the
index says a site has, we already have. The feeds are high quality (the host is
already vetted) and the probe rate is the best of any channel (91%), but the
new-feed yield is **6 added feeds per 100 hosts asked**. Extrapolated, the
remaining ~16,200 never-asked single-feed hosts are worth **~970 feeds**, at one
query per second — roughly 4.5 hours of asking for a thousand feeds. `amp
--all` gets ~370 feeds per half-hour pass. So the oracle complements the
directory; it does not replace it. Its other use is fixing hosts we carry on one
feed only.

**The 10 skipped, and why** (all counted, none quietly dropped):
- 5 tag-archive feeds of one personal blog (`blog.chand1012.dev/tags/{beginner,
  cars,cli,computer,devops}/index.xml`) — slices of the single stream whose site
  feed we already carry. A site's editorial *section* (a newspaper's desks, a
  podcast archive) is a content unit and stays wanted; a tag slice of one person's
  stream is the index being exhaustive on our behalf. `--max-leads-per-site 6`
  allowed them, so the cap alone does not stop this.
- 3 WordPress comment feeds (`betterexplained.com/articles/…/feed/`,
  `asiapacificreport.nz/news/feed/`, an Edinburgh course blog) — caught by the new
  title rule below.
- 1 RSS serialization of a feed we carry as Atom (`adambien.blog/…/entries/rss`
  vs `…/entries/atom`), and 1 legacy libsyn URL of a podcast we add under its
  current URL (`feeds.libsyn.com/150914/rss` = `anglotopia.libsyn.com/rss`).

**Tooling found by this tranche: comment feeds with ordinary-looking URLs.**
`NOT_WORTH_CARRYING` only knew the WordPress shapes (`/comments/feed`,
`/feed/comments`, `/comments/rss`). Two other shapes walk through it:
- Blogger puts a post's comment feed at `/feeds/<post id>/comments/default`.
  Five arrived from one site. The rule now matches `comments/(default|full|rss2|
  atom)`, keyed on the `/comments/` segment and never on `/feeds/`, because the
  same Blogger site publishes its **content** at `/feeds/posts/default`.
  Across the 500 hosts this caught 20 more comment feeds (45 dropped vs 25).
- WordPress titles a comment feed `Comments on: <post title>` while its URL is an
  ordinary `/articles/<slug>/feed/` path. No URL shape reveals it; the items do
  (`By: joshua`, `By: jasa pembuatan website sekolah` — comment spam). Checked in
  `cmd_tag`, where the title is one we read from the fetched body, and anchored on
  the colon so a discussion feed genuinely named "Comments on the State of the
  Union" survives. It dropped 10 rows across the candidate set.

5 new tests, 140 total, each failing without its fix (verified by reverting on a
copy). The pile-up fix from earlier in this session is why no pile-up pins were
needed here: 8 of the 30 new rows carry two topics and every one is a decision,
not a headline keyword.

**Catches the human read made** (the reason the tagger is not left alone):
- `DTN UNHINGED` — "DTN" is Daily Tech News, and its items are `Gaal Vs Aiava |
  WTA VS ATP`: a tennis show. `topic:sport`, not tech.
- `8-4.jp/ja/feed/` is the Japanese-language twin of the English feed we carry.
  TAGS.md says naming the language is what tells two feeds on one host apart, so
  it carries `language:japanese`.
- Five Edinburgh University blogs share one host, but each is its own publisher,
  so each got a URL rule; a host rule would stamp one blog's subject on all.
- `premium.boingboing.net/feed` and `feeds.allenpike.com/feed` are mirrors of
  feeds we already carry; `bif.rs/feed/atom/` is the Atom serialization of a feed
  we carry as RSS; `api.flickr.com/…/photos_public.gne` ("Uploads from everyone")
  is a firehose, not a publisher — and no photography tag exists, so there is
  nothing honest to call it.

## Tranche 19: the amp directory again, and a language gap found mid-tranche (2026-11-04)

| | |
|---|---|
| candidates (`amp --all --limit 1500 --max-per-host 2`) | 1,499 (26,265 already probed skipped; 85,765 dropped by the per-host cap) |
| answered as a real feed | **1,371 (91%)** |
| taggable by the tagger | 415 → **414 merged**, 1 declined |
| left for a human | 952 new rows in `data/DISCOVERY_UNTAGGED.jsonl` (queue now 2,233) |
| hand corrections written | **20 URL rules** (overrides 23,376 → 23,396) |
| product | **31,951 → 32,365 feeds**, 0 removals, 0 pre-existing rows changed |
| harvest | 34,740 → 35,154 records; 11 regressions flagged, none removed |

**No pile-up pins needed for the second tranche running.** 138 of the 414 new rows
carry two or more topics, and every one is a decision — a hand URL rule, a human
host rule, or the feed's own name and description. Since d342fac the headline
rules cannot add a topic to a feed that already has one, and `cmd_tag` only ever
tags a *candidate* from its own name and description, so the pile-up has two
independent doors closed. Nothing to pin.

**20 wrong tags, found by reading the description and items.** The rules guess
from words; these are what the words got wrong: a Basra university journal tagged
`topic:infrastructure` (its papers are maritime insurance, Iraqi environmental
law, drug-control law — it is a **law** journal, now `topic:legal`); a Spanish
overnight radio show tagged `topic:web-development`; a Radio 24 consumption
programme tagged `topic:ai`; two Báo Hưng Yên sections (education, entertainment)
both tagged `topic:food topic:military`; an author advocate/publisher tagged
`topic:tech-industry`; a purpose-of-life podcast tagged `topic:food` because it is
called *Built to Thrive*; a personal blog tagged `type:vendor-blog` while its own
description says "this is my personal space". Amar Ujala's city desks got
`topic:news type:publication language:hindi region:india` — Devanagari is not in
`LANG_RULES` either, so that language had to be written by hand.

**One declined, not banned:** `btccasinonews.com/feed/` — "Crypto casinos,
honestly reviewed", items are trading-program reviews. Affiliate content, not a
publisher. Not merged; not added to `spam.jsonl` (that would be a ban nobody
asked for). If the owner wants it banned so it stops being re-offered, that is one
line in `spam.jsonl`.

## The language gap this tranche exposed (fixed separately, commit f54b133)

Reading the tagged rows showed foreign feeds with no `language:` tag at all — and
the reason is structural: `LANG_RULES` can only see a language through its
**script** (Hangul, kana, Han, Arabic, Cyrillic), so every Latin-script language
is invisible to it. Measured on the shipped file: **1,448 feeds on a
strong-language ccTLD had no `language:` tag while 1,711 identical-shape feeds
did** — and TAGS.md omits `language:` for English, so `beispiel.de/feed` with no
tag reads as English to anyone browsing.

Fix: `classify.CC_LANG` (ccTLD → language), the twin of the existing ccTLD →
region map, applied **after** the script rules so text evidence outranks the
domain (a Russian-language feed hosted in Germany stays `language:russian`).
**1,757 shipped feeds gained exactly one language tag**; 5,611 → 7,368 carry one.
Diff review: zero non-language changes, zero removals, and the 146 feeds that
already carried two language tags stayed at 146 — a new guard in `merge_tags`
stops the rules giving a second language to a feed that names one, which is what
would otherwise have happened to `112.ua/en/rss.xml` (`language:english`, on `.ua`).

Four registries were dropped from the map after reading the feeds they would have
tagged, not on principle: `.ch` (200ok.ch is an English-language dev consultancy),
`.is` (alastair.is, alec.is are English personal sites), `.tw` (404.tw is
Gea-Suan Lin, who writes in English), `.bg` (the Bulgarian-hosted papers here are
the Turkish-language minority press — Bizim Gazete, Bakış). English-publishing
registries (`.in`, `.sg`, `.za`, `.ph`) were never in it.

**Two gaps this found and did not fix, recorded so nobody re-derives them:** the
Cyrillic rule labels Bulgarian feeds `language:russian` (168 Chasa, 24 Chasa),
which a data pass could correct but this rule deliberately does not; and
Devanagari, Thai, Greek-alphabet-but-not-Greek and Hebrew have no script rule at
all, so `language:hindi` on the Amar Ujala feeds above is hand-written.

## Tranche 20: the amp directory, third pass (2026-11-04)

```bash
python3 tools/discover.py amp --all --limit 1500 --max-per-host 2
```

| step | count |
|---|---|
| directory entries | 546,502 |
| dropped: already probed | 27,775 |
| dropped: per-host cap | 85,658 |
| candidates this run | 1,497 |
| served a real feed | 1,333 (**89%**) |
| taggable | 370 |
| still untagged (needs a human) | 3,183 |
| merged | **370** (369 from this run + 1 leftover oracle lead) |
| declined / parked | 4 (below) |

Product 32,365 → **32,735 feeds**, 23,673 → 23,969 hosts, 32,367 titled, 7,487
language-tagged. Zero removals, harvest +370 records.

Declined, and why: `cafelatteau.substack.com` is an erotica feed and TAGS.md has no
`sexuality`/`adult` tag — that is the owner's open policy call, so it stays in the
untagged queue rather than me minting a tag to hold it. Five
`blog.chand1012.dev/tags/<t>/index.xml` rows are one person's single stream sliced
by tag, not five content units (the tranche-18 rule). `btccasinonews.com` was
declined in tranche 19 and keeps coming back because it is still sitting in
`data/candidates.tagged.jsonl`; `feeds.libsyn.com/150914/rss` is the legacy
duplicate skipped in tranche 18. **Both will come back again** until either they
are banned in `spam.jsonl` (an owner decision) or a declined-URL list exists —
there is no such list yet, so every tranche re-offers them.

### A bad HOST rule, found by seeing the same nonsense pair twice

Two feeds in this batch — Hưng Yên papers' transport desk and National Assembly
desk — carried `topic:food topic:military`, the same pair tranche 19's queue pass
had corrected for two other sections of the same site. Not a coincidence: there is
a **host rule** in `overrides.jsonl`, written by an earlier queue pass, reading

```json
{"key": "baohungyen.vn", "tags": ["region:asia","topic:food","topic:military","topic:news","type:publication"]}
```

Someone listed two sections of a Vietnamese provincial daily and stamped them on
the whole domain. It touches 23 feeds and is **right for exactly two** —
`am-thuc` is cuisine, `an ninh - quốc phòng` is public security and national
defence — and wrong for everything else: the travel, investment, administrative
reform, heritage, cultural-life, lifestyle and reader-pages desks are neither about
food nor about the military. 13 shipped feeds carried `topic:military` because of
it. Replaced with the rule the site actually is (`topic:news type:publication`)
plus a URL rule per section, read from the section name. The two sections the old
rule happened to be right about were pinned first, so the correction takes away
nothing that was true; `--allow-type-change` was used because dropping the pair IS
the decision, and `rebuild --write` reported every displaced tag.

The lesson for queue passes: a host rule is a claim about every feed on the host.
A queue pass that reads one section's subject and writes it at host level
generalizes a coincidence, and nothing downstream can see that — the feeds all look
internally consistent.

### Also corrected this tranche, each from the feed's own description

`bulinews.com/news/rss.xml` was `type:vendor-blog` for a football news site;
`canadianzionistforum` was `topic:science` ("the status of the Jewish people in
Canada"); `captainpaulwatson` was `topic:books topic:security` (ocean writing,
biocentrism — Sea Shepherd); `cancelme.substack.com` was `topic:security` ("hot
takes and cringe vulnerability"); `cachemiss.xyz` was `topic:mathematics
type:vendor-blog` (CUDA and GPU posts); `carfreeamerica` lacked `topic:transport`
("City Planning and Transportation Policy"); `canadahealthwatch` lacked
`topic:health`; `cabreza` gained `topic:infrastructure topic:software-engineering`.

Two of my suspicions were **wrong** and the rules were right: `California
Meditation` really is Chinese ("不定期發佈矽谷灣區的社會觀察碎碎念") and `The Tanton
View` really is football ("In-depth football analysis… tactics, squad-building").
Fetching the description before writing a rule is what settles that, and it is 15
seconds of network for a whole batch.

`azadhindtimes.com` took a host rule with `language:hindi` because Devanagari still
has no script rule — that gap is now hit a third time and is the cheapest remaining
structural fix (with a `marathi` keyword rule first, since Marathi also writes
Devanagari).

## Tranche 21: fourth amp pass, and the description-reading pass pays for itself (2026-11-04)

```bash
python3 tools/discover.py amp --all --limit 1500 --max-per-host 2
```

| step | count |
|---|---|
| directory entries | 546,502 |
| dropped: already probed | 29,280 |
| candidates | 1,495 |
| served a real feed | 1,402 (**94%** — best of any tranche) |
| taggable | 313 |
| merged | **312** |
| declined | 1 (`casinokrisa.substack.com`: casino handle + generic SEO marketing listicles) |
| still untagged | 4,264 |

Product 32,735 → **33,047 feeds**, 23,969 → 24,207 hosts. Zero removals. 23 hand
rules; fixed point byte-identical; 148 tests; `--strict` exits 0.

### Three topics are noise magnets

Read from each feed's own description, 22 of 313 rows needed correcting — the same
rate as tranche 19's 20/415. What fools the word rules is not obscure vocabulary, it
is **cognates in prose**:

| shipped tag | the phrase that caused it | what the feed is |
|---|---|---|
| `topic:ai` | *"Dritti **ai** Diritti"* | Italian: "ai" = **"to the"**; a newsletter explaining one right at a time |
| `topic:environment` | *"threat **environment**"* | CASIS *Secure Line*: Canadian intelligence |
| `topic:food` | *"**Wineskins**"* | a Catholic radio program (wineskins = the biblical image) |
| `topic:science` | *"behold God's presence"* / *"any kind of stuff"* | a contemplative newsletter; a personal bearblog |
| `topic:tech-industry` | *"role playing game"*, *"cat ladies"* | two board-gaming podcasts; a political comedy show |
| `topic:history` | *"long historical series"* | a video-game review show |

So `topic:ai`, `topic:science`, `topic:history` and `topic:tech-industry` are the
magnets: they are the words most likely to appear incidentally in prose about
something else. A queue pass that reads only titles will keep re-introducing these.

### Why Amar Ujala's city desks say `topic:education`

`amarujala.com`'s host rule is **correct** (`topic:news type:publication
language:hindi region:india`), yet 22 shipped feeds carry `topic:education` and this
tranche's two new desks arrived tagged `topic:education topic:politics`. The
mechanism is the deliberate bootstrap asymmetry: a **host rule may settle `type:`
but may not supply topics** (the `youtube.com → topic:science` defect, AGENTS.md),
while for a feed with **no tags yet** the keyword rules are allowed to bootstrap
topics — and they read **item headlines**. Every Amar Ujala city desk publishes under
one generic site title ("Latest And Breaking Hindi News Headlines…"), so the only
text available is today's headlines: `tagWhy` for `bhilwara.xml` literally says
`["topic:election", "topic:education"]`.

Not a bug — but it means **any site whose feeds share one boilerplate title gets its
topics from that day's news cycle, permanently pinned.** Two new desks pinned by hand
this tranche. The open structural question, recorded not yet fixed: when a human host
rule already names a topic, should headline keywords still be allowed to bootstrap
topics for a new feed on that host? The youtube.com case says host-rule topics are
untrustworthy; the amarujala case says headline topics are untrustworthy. The fix is
probably per-rule trust (a host rule written from the site's own front page vs one
guessed from a section), which the data model does not currently record.

### The query-string matcher, measured

`classify.py:360` matches a URL rule as `url.startswith(key + "?") or url == key`: a
rule written without a query deliberately covers query-bearing variants. Needed for
tracking parameters; hazardous where the query **is** the section (`norm_key` keeps
`sectionId`, so those are distinct feeds — my `casis.substack.com/feed` rule fired on
`feed?sectionId=185584`). Measured: **10,998 URL rules have no query and only 2 speak
for more than one query-identified feed** (euronews ×4, babbel ×2 — both correct for
every variant), so the exposure is small but it is not zero. Also measured: **69 URL
rules match nothing at all** — inert residue of feeds removed in earlier passes. Not
deleted (deleting rules is a human decision, and they cost nothing), listed here so a
future pass can review them as a set.

### Still unmerged, and the recurring-decline problem

**40 tagged rows from other sources** (oracle, sibling, earlier amp runs) sit in
`data/candidates.tagged.jsonl` and are not in the product; this tranche merged only
its own amp rows. They need their own read before merging — the tagger is right ~94%
of the time and the failures are exactly the word-sense class above.

`casinokrisa` now joins `btccasinonews.com` and the legacy libsyn duplicate as
declined-but-still-offered feeds. Three declines, no declined-URL list: until either
`spam.jsonl` bans them (owner decision) or `add.py merge` consults a declined file,
every tranche re-offers them and every tranche has to re-decline them.

## Tranche 22: fifth amp pass (2026-11-04)

| step | count |
|---|---|
| candidates | 1,499 |
| served a real feed | 1,361 (**91%**) |
| taggable | 392 |
| merged | **392**, nothing declined |
| hand rules | 36 |
| still untagged | 5,228 |

Product 33,047 → **33,439 feeds**, hosts → 24,530. **Zero removals, zero
pre-existing rows changed**, fixed point byte-identical, `--strict` 0, 148 tests.

**Word-sense again, and it is cheap to beat.** 34 of 392 rows (9%) were wrong, all of
them visible only in the description: `topic:food` on a **VFX/3D blog** called *CGI
Coffee*; `topic:programming` on a **recipe** newsletter because the author's handle
is *Chef*; `topic:hardware` on a **chess** newsletter called *The Chess Circuit*;
`topic:web-development` on a **philosophy** newsletter (*Fear Is a Liar*) and on a
**French school radio** show; `topic:music` on a **comedian's** show; `topic:history`
on a **Duke basketball** podcast because its own blurb says *"a legacy … history"*.
Fetching 36 descriptions at 1 request/s costs about 40 seconds and settles all of it.

**A host rule of my own, and decide.py caught me writing it badly.** The Duke desk
came out `topic:history`; every other Beatline feed on the same host came out
`sport`. The right fix is one host rule (`cdn.beatlinesports.com → topic:sport
type:podcast`), and I first wrote it as `https://cdn.beatlinesports.com` — scheme, no
path. `decide.py` refused: *"URL rule with no path matches one exact URL; a host rule
(no slash) is usually what is meant."* The validator is earning its keep on my own
mistakes, not just the tagger's.

**Amar Ujala for the third tranche running.** Two more city desks
(`bhind`, `bhiwani`) arrived bootstrapped from that day's headlines
(`topic:business topic:politics`, `topic:education topic:politics`) and pinned by
hand. Nine desks pinned across three tranches; the host rule is right and the
bootstrap path keeps going around it. If a sixth tranche brings two more, the
cumulative cost has passed the cost of answering the structural question in
DISCOVERY.md (tranche 21).

**One false alarm worth recording, because it will recur.** Two Bhaskar rows looked
like they were missing `language:hindi` in `data/candidates.tagged.jsonl`. They are
not: all 25 `bhaskar.com` rows in the product carry it. The candidate file shows only
the tags the *tagging* path decided and omits what a **host rule** contributes
(`language:`, `region:`) — rebuild adds those later. Check the product, never
`candidates.tagged.jsonl`, when asking whether a tag is present.

## Tranche 23: the `topic:media` catch-all, and a note about accusing the wrong file (2026-11-04)

| step | count |
|---|---|
| candidates | 1,500 |
| served a real feed | 1,342 (89%) |
| taggable | 397 → **419** after the rule fix |
| merged | **419** |
| hand rules | 6 |
| untagged queue | 6,168 → **6,078** (it went *down*) |

Product 33,439 -> 33,858 feeds, 24,530 -> 24,874 hosts. Zero removals, zero pre-existing rows changed,
fixed point byte-identical, `--strict` 0, **153 tests**.

### A whole tranche read as podcasts, not as subjects

Reading this batch, 292 of 397 taggable rows carried a magnet topic, and the dominant
one was `topic:media`: `Bram FM`, `Chubstep`, `Gray Areas`, `Cigar Hacks Podcast` … and
**~40 church feeds** — `Christ Church Bentonville`, `River Church Sermons`,
`Predigten der Christus-Gemeinde` — sitting at `topic:media` while 415 other
church feeds in the product carry `topic:religion`.

Two causes, both in `classify.py`:

* `TOPIC_RULES` had **no religion rule at all** — `religio` is the only form the
  tagging path knew, so a feed named *Church … Sermons* matched nothing about
  churches.
* It did match `(podcast|episode|\baudio\b|interview with|listen to) → topic:media`.
  Every matching rule is kept, so the medium became the subject. `topic:media` names
  how a feed is delivered, not what it is about — it is the catch-all AGENTS.md says
  not to reintroduce, reached by accident rather than intent.

**Fix:** the medium is now a **last resort**. `suggest()` collects every rule that
fired; if any subject rule fired, `topic:media` is dropped; if nothing did, it stays —
a feed that is only ever "an audio show about things" still gets a topic instead of
flooding the human queue. Plus a religion rule with word boundaries and the
non-English forms this very batch contained (`predigten`, `kirche`, `kerk`, `église`).

Measured on this tranche: `topic:media` rows **165 → 69**, `topic:religion` **2 → 73**,
taggable rows **397 → 419** (22 feeds gained their first real subject), untagged queue
**down** by 90. No row lost its only topic; 96 rows lost `topic:media` and kept or
gained a subject. `5` new tests, each half failing without its half of the fix (2 fail
without the last-resort guard, 3 without the religion rule).

**The product did not move.** `classify.py && rebuild.py --write && cmp` was
byte-identical, because `merge_tags` protects tags already in `feeds.json` — the fix
changes what *new* candidates get, not what shipped rows keep. So the ~96 shipped
church feeds still say `topic:media`; correcting those is a reviewed data pass like the
pile-up retro-clean, not something to do by shipping a rule change.

### My own rule made one false positive, and it is in the batch as a hand rule

`Church & Street Foto Club` — *"street photography, travel, self-discovery, and
occasionally, cameras"* — is a photo newsletter on **Church Street**, and the new
religion rule claimed it. It is pinned by hand with `topic:design topic:travel` and
recorded here, because a rule that fixes 40 rows while breaking one is only honest if
the one is written down. (`The Churchill Society` is why `\bchurch(es)?\b` has a
trailing boundary — the first version matched the prefix of *Churchill* and the test
for it exists so nobody removes the boundary.)

### The wrong accusation, recorded so it is not repeated

I first blamed `discover.py:146` (`(r"podcast", ["topic:media"])`) for this. Wrong:
that table (`CATEGORY_TOPICS`) runs on a curated **list's outlines only**, and its own
comment spells out that a feed's name is never fed to it — the comment even cites
*"Apple Weekly" becoming topic:gadgets* as the reason. The real culprit was the
same-shaped rule in a different file. Grepping for a string and then reading the code
*around* it is the step that matters: two identical rules, one innocent.

## Tranche 24: +447 feeds, and the spam rule quietly deleted a real feed (2026-11-04)

| step | count |
|---|---|
| candidates | 1,498 |
| served a real feed | 1,380 (**92%**) |
| taggable | 447 (largest batch of the session - the topic:media fix raised the taggable fraction) |
| merged | **447** |
| hand rules | 15 |
| untagged queue | 7,004 |

Product 33,858 → **34,305 feeds**, 24,874 → 25,251 hosts. Zero removals, zero
pre-existing rows changed, fixed point byte-identical, `--strict` 0, **156 tests**.

The church feeds that were `topic:media` in every prior tranche now carry
`topic:religion` (the tranche-23 fix); the large climate block reads right. This is
the highest-quality batch of the session.

### The rule deleted a feed I had just merged, and I caught it

After the merge, `feeds.json` had 34,305 rows. After the settle, it had **34,304**
with 0 reported removals. One row had vanished. Following it:

* It was in `harvest.jsonl` (fetched, status 200, valid XML).
* It was **not** in `draft.jsonl`, so classify had not written it.
* It was not a `norm_key` duplicate.
* `triage.jsonl` said: `remove` — `spam:casino-seo:in-feed-name`.

The feed was **`https://climatecasino.substack.com/feed`**, "The Climate Casino" —
Prof. Eliot Jacobson's newsletter on *the collapse of global industrial civilization
and the sixth great extinction*. It is a climate feed. "Casino" is a metaphor for the
climate gamble. The `casino-seo` spam rule saw the word in the feed's **name** and
removed it, and `rebuild.py` applied the verdict silently.

**That is the invariant broken**: a code path removed a feed a human (this pass,
having read the 447 tagged rows) had just deliberately added.

### Why the rule misfired, and the fix

`triage.py`'s `SPAM_PATTERNS` has `casino-seo`, whose word list includes `casino`, and
a spam term in a feed's **name** is damning on its own. That is true of pharma words
(`viagra`, `cbd oil`) — no legitimate feed is named for those — and of the two words
already fixed by `NAME_EXEMPT_WORDS` (`porn`, `xxx`; a recovery podcast and a Roman
numeral). `casino` is a **fourth** word in the same class: a common English word that
can be a metaphor, a proper noun, or an entertainment reference in a real feed's name.

Fix: a new tier, `NAME_CORROBORATED`. A gambling word in a feed's name removes only if
the **body corroborates** it (≥1 gambling hit in the items). `The Climate Casino` has
zero gambling words in its items, so it is no longer removed. This is deliberately
**stricter** than `NAME_EXEMPT_WORDS` (which ignore the name and demand the full ≥3
item count): a real casino feed whose name says "casino" and whose items mention
gambling even once still goes, so the fix does not weaken detection. The existing
`test_a_real_casino_hijack_still_goes` is caught via item hits, not the name, and
still passes. Three new tests pin it: the climate feed survives; a casino feed with a
name hit + one gambling item is removed; a "Casino Night board game show" with no gambling
anywhere survives.

### Blast radius: one feed, and the class is now closed

Searching the removal record, `casino-seo:in-feed-name` had **two** prior false
positives — `benuyama.com/.../quit-porn-with-ben-uyama/` (a nofap recovery podcast)
and `biblialiturgia.com/feed/` (a Roman-numeral lectionary) — both already fixed by
`NAME_EXEMPT_WORDS` in an earlier tranche. `The Climate Casino` was the **third**, the
first on `casino` itself. It is the only `casino-seo` removal in the current product;
no other legitimate feed was lost to it.

### The restore

Restored by re-merging the **single row** (a full re-merge of the 447-file would have
written 446 spurious `overrides.jsonl` lines, since merge treats an already-present
candidate as an override candidate). After the rule fix, triage now returns `keep | ok`
for it and the settle removes 0, so the pass's `REMOVED.md` was reverted to HEAD —
which still accurately records the `blog.bitsrc.io` removal from an earlier revision.
Final: 34,305 feeds, all 447 candidates present, climatecasino back.

### The structural gap this exposes (recorded, not fixed here)

`add.py merge` adds on a human's review; `triage` + `rebuild` can then **subtract** on a
pattern's verdict, with no per-feed human in between. The spam pattern is a human-written
rule, but it fired wrongly on a specific feed, and the only reason that was caught is
that the count (34,305 → 34,304) was checked against the merge. A feed with a name that
trips a *different* pattern could vanish with no count mismatch to spot (if it were the
only removal and REMOVED.md is read, it is caught; but the settle did not print it).
A candidate guard, left to the owner: a pattern-based `remove` of a feed that is **new in
this pass** (absent from HEAD's `feeds.json`) should `flag`, not `remove` — a feed that
just cleared a human review is not the pattern's to delete. That needs a git baseline in
triage, which is a design change, not a tranche edit.

## Tranche 25: +381 feeds, the cleanest batch yet, and a Dutch sermon the rule missed (2026-11-04)

| step | count |
|---|---|
| candidates | 1,499 |
| served a real feed | 1,368 (91%) |
| taggable | 381 |
| merged | **381** |
| hand rules | 19 |
| untagged queue | 7,985 |

Product 34,305 → **34,686 feeds**, 25,251 → 25,557 hosts, 34,318 titled, 7,741
language-tagged. Zero removals, zero pre-existing rows changed, fixed point
byte-identical, `--strict` 0, **157 tests**. Every merged candidate present in the
product (the count guard below).

This is the **cleanest batch of the session**: every church feed carries `religion`
(the tranche-23 fix holds across two tranches now), and most `media` rows are the
correct last-resort. 19 hand rules, the usual word-sense class: "Coffee & Commits"
tagged food (a programming blog), "Commodities Predict" tagged food (coffee is one of
the commodities), "CommonsWare" tagged books (it is an Android development blog),
"Connected by data" tagged sport (a data initiative), a psychiatrist tagged
`topic:tech-industry`, a Polish ultra-running podcast tagged media, three football
podcasts (Ajax, Schalke's 2. Bundesliga talk, Bayern) tagged media, and an OADC
criminal-case-law podcast tagged media.

### A Dutch sermon the religion rule missed, closed at the rule not the row

One church feed fell through to `topic:media` anyway: `Rafaël gemeente "De Rank"`,
whose description is *"Dit kanaal bevat de preken die op zondagochtend in onze
gemeente worden gehouden"* (this channel contains the sermons held Sunday mornings in
our congregation). The tranche-23 religion rule knew the German (`predigt`) and French
(`prêche` via `église`) word for sermon but not the Dutch one.

Fixed at the rule: added `pree?k\w*`. Two forms exist and the first attempt
(`preek\w*`) matched only the singular — the doubled *e* collapses in the plural, so
`preek` is p-r-e-e-k but `preken` is p-r-e-k-e-n, and `pree?k\w*` is what catches both.
`gemeente` was **deliberately not** added: in Dutch it also means *municipality*, so a
municipal feed would become a religion feed. One test pins the Dutch case; product
byte-identical (the rule change touches only new candidates). The feed now tags
`religion` with no hand rule.

### The count guard is now a standing check

The only reason tranche 24's silent deletion was caught was comparing the settled
count against the merge (34,305 → 34,304). From this tranche on the settle
explicitly checks that **every merged candidate is present in the product** before it
is called done. This tranche: 381 merged, 381 present, 0 missing. A feed that tripped a
spam pattern would have shown up as a missing row the moment it was dropped.

## Tranche 26: +398 feeds across 35k, and the highest correction rate of the session (2026-11-04)

| step | count |
|---|---|
| candidates | 1,498 |
| served a real feed | 1,316 (88%) |
| taggable | 398 |
| merged | **398** |
| hand rules | **102** (26% of taggable) |
| untagged queue | 8,900 |

Product 34,686 → **35,084 feeds**, 25,557 → 25,884 hosts, 34,716 titled, 7,790
language-tagged. Zero removals, zero pre-existing rows changed, fixed point
byte-identical, `--strict` 0, 157 tests. Every merged candidate present in the product.

**The correction rate was the highest of the session: 26%**, against the ~7–9% of
tranches 22–24. The cause is visible in the corrections: this AMP slice is heavy in
personal podcasts with evocative names, and the headline/topic rules key on
word-senses the feed does not have. The four noise magnets account for most of it:
`topic:science` on a therapist ("Sister Kana"), `topic:ai` on a data newsletter,
`topic:tech-industry` on a self-care newsletter, `topic:hardware` on a Marvel podcast,
`topic:history` on a DSA chapter and a basketball feed. `topic:food` came from the word
coffee twice (a chartered-accountant podcast, a commodities feed) and from an OB/GYN
study podcast ("CREOGs Over Coffee"). Several church-adjacent and DJ-show feeds fell to
`media` as the correct last-resort but were still pinned for the obvious subject
(football, case law, 808 hip-hop, ham radio, Star Wars, MCU).

Two vocabulary gaps surfaced and were closed by mapping, not by adding tags:
**there is no `topic:crypto`** (mapped to `finance`), no `topic:consumer-electronics`
(mapped to `gadgets`), no `topic:engineering` (mapped to `systems`), and no
`topic:self-improvement` (mapped to `personal`). `decide.py` rejects a tag outside
TAGS.md, which is what caught all four in the same run. Whether `crypto` deserves its
own topic is a real question now — it is the third tranche in which a crypto feed had
to be mapped to finance — but that is a TAGS.md change, not a tranche edit.

Languages read from the feed's own content: Dutch (weight-loss, nutrition medicine,
information-archivists, sewing, animal communication, a Münster radio show), German
(economics ×2, copywriting, comedy, a 2. Bundesliga-adjacent show), Japanese (a labour-law
podcast for business owners, a pro-baseball commentary), Czech, French (horoscopes,
teacher AI tools, traditional music), Spanish (solopreneurs, a housing cooperative),
Portuguese (Brazilian football).

## Tranche 27: +413 feeds across 26k hosts, and the session's worst correction rate (2026-11-04)

| step | count |
|---|---|
| candidates | 1,499 |
| served a real feed | 1,366 (91%) |
| taggable | 413 |
| merged | **413** |
| hand rules | **141** (34% of taggable) |
| untagged queue | 9,842 |

Product 35,084 → **35,497 feeds**, 25,884 → 26,233 hosts, 35,129 titled, 7,857
language-tagged. Zero removals, zero pre-existing rows changed, fixed point
byte-identical, `--strict` 0, 157 tests. Every merged candidate present in the product.

**Correction rate 34%, the worst of the session and worse than tranche 26 (26%). The
AMP directory's tail is where the word-sense misfires concentrate, and it keeps
getting worse: tranche 26 was 26%, this one 34%. The same four noise magnets, the same
coffee→food pun (a bookstore and a video-game café both sit on a host whose name
contains "Coffee"), and a long tail of `media` last-resort rows pinned for the obvious
subject (curling, wrestling, crossfit, cycling, a Hungarian CV-coach, a Dutch
water-dam podcast, a German hockey podcast, an Italian materials podcast, two
NRJ horoscopes).

Two new vocabulary confirmations: **crypto still has no topic of its own** — this
tranche mapped seven crypto feeds to `finance` (a new record, versus three running
total last tranche). The case for a `topic:crypto` in TAGS.md is now unambiguous.
And **`topic:gadgets`** (added in an earlier vocabulary pass) absorbed the consumer-
electronics row (an Italian materials/minerals podcast). `decide.py` rejected every
out-of-vocabulary tag in the same run; nothing invalid reached `overrides.jsonl`.

Languages read from content: Czech ×3, German ×4, French ×3 (incl. two more NRJ
horoscopes), Dutch ×2, Japanese ×3, Hindi, Russian, Greek, Romanian, Hungarian ×2,
Portuguese, Spanish, Italian, Turkish. The NRJ horoscope pattern (one feed per zodiac
sign) is now in three tranches; it is a site, not a feed set, so each sign feed is
pinned individually.

## Tranche 28: +267 feeds, and my own hand rules corrected (`topic:astrology` already existed)

| step | count |
|---|---|
| candidates | 1,499 |
| served a real feed | 1,287 (86%) |
| taggable | 267 |
| merged | **267** |
| hand rules | 113 (42% of taggable) |
| pre-existing rows retagged | **8** (all deliberate) |
| untagged queue | 10,850 |

Product 35,497 → **35,764 feeds**, 26,233 → 26,440 hosts, 35,396 titled, 7,908
language-tagged. Zero removals, fixed point byte-identical, `--strict` 0, 157 tests,
`REMOVED.md` unchanged, every merged candidate present in the product.

### The correction of a correction: `topic:astrology` was in TAGS.md all along

Nine feeds named *L'horoscope* / *L'Horoscope NRJ* sat in the product split **three
different ways**: two old ones correctly carried `topic:astrology` (which TAGS.md
defines explicitly as "horoscopes, natal charts, astrological practice — a real
recurring cluster"), three carried `topic:news topic:travel` from headline rules that
keyed on words inside horoscope prose, and **four carried `topic:entertainment` because
of my own hand rules in tranches 26 and 27** — I pinned the subject from the description
without checking whether a topic for it existed. All nine now agree on `astrology`.

That is a new failure mode for this notebook: not a rule keying on the wrong word-sense,
but **a human decision that invents a tag instead of using the one the vocabulary
already has.** The fix in practice: before writing a hand rule for an obvious subject,
grep TAGS.md for it. It cost nothing here (8 rows, one tranche), but four of those rows
were shipped by me with a tag I'd have rejected if a rule had produced it.

**One near-miss caught by checking the feed before shipping.** Collecting the shipped
horoscope feeds by title also picked up `balado.ckrl.qc.ca/radioshows/1156`, a Québec
City radio segment. My drafted rule said `region:france` — wrong country for Québec
radio — and would have silently dropped `topic:media` and `topic:music` that an earlier
pass shipped. Rewritten additively (`region:canada` restated, old tags kept,
`astrology` added), the row gained one tag and lost none. The lesson generalises:
**a retag written for a *pattern* of feeds must be checked against each already-shipped
member of the pattern**, because the shipped ones have history the new ones do not.
`rebuild.py`'s `override replaced N tag(s)` line is what makes that visible — the CKRL
row correctly does not appear in it.

### Correction rate: 42%, and still climbing

7–9% (tranches 22–24) → 26% (26) → 34% (27) → **42% (28)**. The AMP tail is now more
mis-tags than tags, and the causes repeat rather than diversify: `coffee` → food (a
tarot podcast, a German psychology show), `Data` → food ("Dave's Data", a computer
science blog), `Dairy`/`dairy` → sport and business, four D&D actual-play shows → media,
a Daft Punk photo archive → history, a heavy-metal podcast and two DJ sets → media,
a Star Wars show, wrestling, hockey, NBA, Title IX, real estate, home inspection.

Languages read from content: German ×6, French ×5, Czech ×2, Dutch ×2, Italian ×2,
Spanish, Japanese, Turkish, Vietnamese, Indonesian. `topic:film` does not exist (mapped
to `entertainment`); `decide.py` rejected it in the same run.

## Tranche 29: +307 feeds, two channels tried, and the count guard earning its keep

| step | count |
|---|---|
| candidates | 1,619 (`leads` 121 + AMP 1,499) |
| served a real feed | 1,252 (77%) |
| taggable | 308 |
| merged | **307** (1 refused) |
| hand rules | 115 |
| untagged queue | 11,774 |

Product 35,764 → **36,071 feeds**, 26,440 → 26,683 hosts, 35,703 titled, 7,972
language-tagged, 610 carrying a `topic:programming:<lang>` language tag. Zero
removals, zero pre-existing rows changed, fixed point byte-identical, `--strict` 0,
157 tests, `REMOVED.md` unchanged.

### Why not AMP again, and what the alternative channel gave

After tranche 28's 42% correction rate I tried a second channel in the same tranche:
`discover.py leads` (feed links found on pages of hosts we already trust), which
measured **94% live** when first run. It is now exhausted: it offered only **121**
candidates (11,052 altFeeds already seen, 9,296 already in the product) and those
leftovers served a real feed just **35%** of the time. The good altFeeds have all been
picked. Both channels are now thin: AMP 86–91% live but 34–42% mis-tagged, leads 35%
live and nearly empty.

### The count guard found one feed that did not land — and it was supposed not to

`merged candidates missing from product: 1` → `https://importpython.com/feed/`. It
probed as a real feed (200, `isFeed=true`), was in the merged file, and was not in
`feeds.json`. The reason, printed by `add.py merge`:

> `banned by spam.jsonl: SEO listicle farm under a Python name: fitness app dev
> companies, crypto licence services, VASP compliance`

**A prior human decision, honoured.** `add.py` refuses candidates that `spam.jsonl`
bans precisely so a stale candidates file cannot re-admit what a human removed. This is
the standing declined-URL problem seen from the good side: the ban was written down, so
the reappearance was caught. The three cases where I could only report a repeat
(`btccasinonews.com`, `casinokrisa`, the legacy libsyn duplicate) were repeats *because*
nothing was written down. importpython.com is the fourth reappearance and the first one
the system stopped by itself.

### Two false conclusions of my own, both from how I inspected tags

Worth writing down because they cost detours and both were wrong:

1. My tag printer showed a topic as `t.split(':')[-1]`, so
   `topic:programming:python` displayed as **`python`** and I concluded the feed had no
   topic — then wrote a rule to "fix" it. It already had one.
2. To answer "is this tag in the vocabulary?" I ran `grep -oE "topic:[a-z-]+" TAGS.md`,
   which **cuts at the second colon** and so reported that `topic:programming:<lang>`
   was missing — when TAGS.md documents it explicitly (line 32, full list 37–49:
   ada, apl, assembly, c, clojure, cpp, crystal, d, dart, elixir, erlang, fortran,
   fsharp, go, haskell, java, javascript, julia, kotlin, lisp, lua, nim, objective-c,
   ocaml, perl, php, python, r, ruby, rust, scala, shell, smalltalk, sql, swift, zig).

Both mistakes pointed at a "defect" that did not exist. The correct tool for both
questions is `vocab.load()` — it parses TAGS.md with a regex that allows `:` in the
value, and it confirms all 33 language sub-tags are in the vocabulary (174 tags total).
**Ask the code that defines the rule, not a grep that approximates it.**

## Cleanup pass: the double-language defect, and the feeds outside the format contract (2026-11-05)

No new feeds. Product 36,071 → **36,071**, zero removals, **159 tests**.

A read-only audit of the product against `vocab.load()` (not a grep — see tranche 29's
landmine) found three violations of the documented contract:

| finding | count | action |
|---|---|---|
| feeds with two `language:` tags | 146 | 127 fixed, 19 left (correct) |
| feeds with no `topic:`, or not exactly one `type:` | 12 | 3 fixed, 9 left (blocked) |
| feeds with 3 `region:` tags | 1 | left |

### The language precedence defect, and why `language:` joins `type:` at host scope

`merge_tags` had a guard — "a feed has one language" — that stopped **rules**
stacking a second language onto a decided one. It said nothing about the language
already sitting in `keep` from an earlier pass. The mechanism, from an actual row:

```
03352.com.ua  feeds.json held language:russian  (Cyrillic script rule, an old pass)
              a later HOST rule decided          language:ukrainian
              merge unioned the two              -> both shipped
```

129 feeds were this shape — a hand decision beside a rule-derived guess. The fix
extends the host-scope strip from `{type}` to `{type, language}`: a **host** rule has
no business deciding one feed's `topic:` (the `npr.org` rule once stripped
`topic:health` from a section feed), but a site really does publish in a language, so
"this domain is Ukrainian" is a legitimate claim about every feed on it. The displaced
tag is reported by the existing `override replaced N tag(s)` line, never dropped in
silence. `decided_facets` keeps its topic/type contract; `language` is handled in
`merge_tags` so the two precedence stories stay readable apart.

The diff proved the scope before it shipped: **127 rows changed, each losing exactly
one `language:` tag, gaining nothing, nothing else touched, zero feeds added or
removed.** 95 were `russian`→`ukrainian` (`.ua` regional papers), 16 `arabic`→`urdu`
(Pakistani news sites).

**19 double-language feeds remain, correctly.** Every language on them is present in a
hand rule for that URL or host — including two that my first classifier misfiled as
defects because it read `tags` and not **`pathTags`**: `joho-todai.com` (`language:japanese`
for the site, `pathTags: {/en/rss: language:english}`) and `advalvas.vu.nl` (Dutch, with
an `/en/feed` English section). A multilingual host with a per-path language rule is the
system working, and `pathTags` is the third place a tag can come from — audit all three.

### 12 feeds shipped outside the format contract; 3 were readable, 9 are blocked

The contract is at least one `topic:` and exactly one `type:`. Twelve feeds violated it,
none with a title or description in the harvest. Probed: **0 of 12 served a feed to the
harvester.** Checked by hand the way the project requires (`curl --compressed`, browser
UA): **3 of 12 served a real RSS feed** — the harvester was being blocked, not the feed
dead:

- `ahilado.wordpress.com` — *"Math and Physics for Everyone"*, items on Hilbert modular
  surfaces and Higgs bundles → `topic:mathematics topic:science`
- `hanszandbelt.wordpress.com` — *"Stuff on Identity Federation, SSO etc."*, items on
  WebAuthn and OpenID Connect → `topic:security`
- `danielspost.news.blog` — *The Daniels Post*, Daniel Akoh's news blog → `topic:news`

The other nine stay **flagged, not removed** — Cloudflare "Just a moment…" challenges
(403), a 522 origin-down, a 503 "deployment paused", TLS hostname mismatches, timeouts.
Our inability to read them is not evidence they are dead; they join the ~200 blocked
feeds that need a browser, and they remain outside the contract until someone reads them.
Two of them (`aarvik.dk`, `developer.salesforce.com`) carry a topic but no `type:` — a
`type:` could be guessed but would be a guess, so it was not written.

## `topic:crypto` — the vocabulary gap that had been mapped away for four tranches (2026-11-05)

Product 36,071 → **36,071**, zero removals, **162 tests**, `--strict` 0.

Every crypto feed for four tranches was filed under `topic:finance` because the
vocabulary had nowhere else for it — 121 by title/URL, and **385** once the actual rule
ran over the harvest. The tag now exists, with the rule to keep it filled and a reviewed
pass over what was already shipped.

**The rule.** Crypto was split out of the finance regex (which had been matching
`bitcoin|blockchain|cryptocurrenc*` all along) into its own. The word that makes this a
rule rather than a substring match is **`crypto` on its own**: it is how security writers
abbreviate *cryptography*, and a feed titled "Crypto Is Not A Four Letter Word" about key
exchange is a security feed. My own test caught that — the first version fired on it. So
the bare word is not a trigger: a compound ("crypto assets", "crypto market", "crypto
exchange") or an unambiguous term (`bitcoin`, `btc`, `blockchain`, `defi`, `altcoin`,
`stablecoin`, `nft`, `web3`, `satoshi`, `ethereum`, `halving`) is required. Three tests;
revert the split and exactly one fails.

**The retro pass, and where the pile-up would have entered.** 385 shipped feeds match the
rule, but the haystack includes item headlines, which is the pile-up's front door. Split
by signal source, using the same counting discipline the spam rule uses:

| signal | count | action |
|---|---|---|
| in the feed's **own title or description** | **217** | tagged `topic:crypto` |
| one item headline only | 130 | untouched — one mention is not a subject |
| 2 item headlines | 21 | untouched |
| **3+** item headlines | 17 | left for a human look (a newspaper can run three crypto stories) |

For the 217, `topic:finance` was **kept only where a non-crypto money word appears in the
same text** (economy, market, bond, investing, banking…): 44 keep both, 173 become crypto
without finance. Verified before `--apply`: 217 rows changed, `topic:finance` the only tag
lost anywhere, **zero** `type:`/`region:`/`language:` facets touched, zero feeds added or
removed. `--allow-type-change` was needed because 40 of these rows already had a hand rule
naming `finance` — that flag is the record that replacing a previous human decision was
the point of the change, not an accident.

## `topic:real-estate`, and a tag rejected on the evidence (2026-11-05)

Product 36,071 → **36,071**, zero removals, **166 tests**, `--strict` 0.

Measured before adding anything, across every shipped feed's own title and description:

| cluster | feeds naming it | currently filed only under a stretched tag | verdict |
|---|---|---|---|
| mental health | 195 | — | **no new tag**: `topic:health` covers it honestly |
| crafts / DIY | 174 | 37 | **rejected**: mostly already under `design`/`art` correctly, and the regex caught false positives ("DIY" inside a music label's name, DIY *marketing*) |
| real estate | 76 | **64** | **added** |
| fashion | 77 | — | no new tag: `design`/`lifestyle` are not stretches |
| motorsport | 22 | 2 | no new tag: too small |
| physics | 46 | 0 | no new tag: `science` + `mathematics` suffice |

The bar TAGS.md already uses for `comics`, `animals` and `astrology` is *a recurring
cluster that existing tags both stretched*. Real estate cleared it — 64 feeds were filed
under `finance`/`business`/`media` alone. Crafts had volume but not the stretch, so it
was rejected: **a big count is not the test.**

### Two false positives the new rule taught me

1. **`landlord`** fired on *"I'm a normal bloke, a pub landlord"* — in British usage the
   keeper of a public house, not a property owner. Fixed with `(?<!pub )\blandlord\b`,
   pinned by a test.
2. **`nypost.com` gained `topic:real-estate`** because the paper's own description lists
   its sections: *"breaking news, news about New York, sports, business, entertainment,
   opinion, real estate, culture, fashion, and more."* A section-listing description is
   not a subject decision. No heuristic caught it reliably — counting how many other
   topic rules fire returned just 1 — so the pass stayed **reviewed**: all 88 rows read,
   **6 declined** with the reason recorded in `decisions-realestate.txt` (the Post, The
   Atlantic's business section, an agency blog naming real estate among its clients, a
   life-transitions podcast, a macro letter covering the housing market, an
   entrepreneurship show). NY Post still reads `region:usa topic:news type:publication`.

Verified before `--apply`: 88 rows changed, `topic:finance` the only tag lost anywhere
(15 rows, where nothing but property signalled money), zero `type:`/`region:`/
`language:` facets touched, zero feeds added or removed, fixed point byte-identical.

`review.py` now reports **0 judgeable feeds** in the queue and 9 rows with no harvest
data — the nine blocked feeds from the contract pass, still waiting on a browser.

## The blocked feeds were a fingerprint problem, not a politeness one (2026-11-06)

Product 36,071 → **36,066** (8 verified removals, 3 verified successors added),
titles 35,703 → **35,813**, **178 tests**, `--strict` 0.

The ~200 blocked feeds were the largest standing gap, and the plan was a `curl`-style
browser fallback. Measured first, and the plan was wrong: `harvest.py` already sends
browser-ish headers, and the only header that mattered was **the User-Agent version and
platform**. Firefox/97.0 on Windows NT 10.0 is a 2022 browser, and "outdated Firefox on
Windows" is itself a bot tell. Same six URLs, minutes apart: Windows/97 → 403 on all;
Linux/97 → 200; Windows/115 → 200; `curl/8.5.0` → 200. Accept-Language and Accept
q-values changed nothing.

So the fix is one header line, the etiquette is untouched (8 lanes, one host per lane, a
pause), and there is no second fetch path to maintain. `--retry-failed` over all 351
parked URLs recovered **148 feeds and 146 titles** with **zero newly-broken**, and left
10 regressions flagged rather than removed.

### What the recovery then required: reading the removal list

The recovered harvest made 8 feeds removable (2×404, 6 serving `text/html`). All 8 were
checked by hand with `curl -L --compressed` as a reader's client would, and the
`not-a-feed` ones were checked for a declared successor before being cut:

| dead | successor | merged |
|---|---|---|
| `blog.moove-it.com/rss` | `qubika.com/feed/` (the company renamed) | yes, tags carried |
| `feeds.regulargeek.com/RegularGeek` | `regulargeek.com/feed/` | yes |
| `smallwarsjournal.com/rss/blogs` | `smallwarsjournal.com/feed/` | yes |
| `developer.atlassian.com/blog/feed.xml` | named, but the named URL is not a feed | no |
| `asec.ahnlab.com/en/category/malware-information-en/feed/` | `asec.ahnlab.com/en/feed/` — **already in the product** | no (would have been a duplicate line) |
| `insidexpress.com/feed/`, `webuild.envato.com/atom.xml`, `erlang-solutions.com/news.rss` | none declared; homepage names none either | no |

Two near-misses worth recording: adding ahnlab's successor would have **duplicated a feed
already shipped**, and `smallwarsjournal.com/feed/` was refused as `not a feed (403)`
because `probe_results.jsonl` cached a 403 from my own repeat hits minutes after the same
URL answered cleanly with 5 items — the cached snapshot, not the feed, was stale. Clearing
that one record let it merge. `successors.jsonl` is committed as the provenance for which
tags were carried across a move.

Still parked after all this: 78 blocked + 77 unreachable, and the same 9 feeds with no
harvest content — 3 of them TLS `CERTIFICATE_VERIFY_FAILED`, which a header cannot fix,
and the rest Cloudflare JS challenges, which no header fixes either.

## `topic:adult`, and `DOM` meaning a person (2026-11-06)

Product 36,067 (one feed added), **181 tests**, `--strict` 0.

The owner answered the standing policy call: adult content stays, so it gets a tag. 14
shipped feeds tagged by hand and one candidate that had been declined earlier *only
because the vocabulary had no place for it* now merges. 29 shipped feeds contain the
words; 14 are the subject. The declines and their reasons are in `decisions-adult.txt` —
the notable ones being `kink.nl` (a Dutch radio station, plus two of its programmes),
`NSFW` as an advisory line on a history podcast and a Cold War podcast, a musician whose
blog is named after his band, and two recovery podcasts.

TAGS.md now states the two rules that make the tag mean anything:

- it is what a feed **contains**, not what it **discusses** — a pornography-addiction
  recovery podcast is `health`/`personal`, never `adult`;
- **write no classify rule for it.** It is a noise magnet of a kind not seen before: the
  words are band names, station names and advisory boilerplate.

### How the feed that prompted the policy call was tagged in the queue

`cafelatteau.substack.com` ("The Humiliation Journal", BDSM erotica) arrived in
`candidates.tagged.jsonl` as **`topic:web-development`**, with `tagWhy: ["topic:Dom"]`.
The web-development rule contains `\bDOM\b` and every topic rule runs under `re.I`, so it
matched "**Dom**/sub".

Measured before changing anything: shipped feeds carrying `topic:web-development` whose
*only* web token is "dom" — **2**, both people named Dom (one an irrigation contractor
who writes about B-movies, one a networking engineer). Two more named Dom are genuine
Rails/JavaScript writers and keep the tag. A feed truly about the DOM always says
javascript/css/react/html too, all already tokens, so the abbreviation was buying nothing
and cost two false tags plus one absurd one. Replaced with `document object model`;
3 tests, and restoring `\bDOM\b` fails exactly those 3. The two mis-tagged rows were
corrected by hand (both keep ≥1 topic; the 5 rows still without any topic are the blocked
feeds and pre-date this change).

### What the blocked set is made of now

After the User-Agent fix: 78 blocked + 77 unreachable, and 9 feeds still outside the
format contract. Breaking down the 9 by cause, since "blocked" was hiding three
different problems: Cloudflare JS challenges (no header fixes these), a `522`
origin-down, a `403` WAF, and **two TLS failures** — `programmingwithmosh.com` presents a
certificate for the wrong hostname, `aarvik.dk` answers `TLSV1_ALERT_INTERNAL_ERROR`.
Those two are reachable only by disabling certificate verification, which is not
something a harvester should do silently: fetched bytes would be stored as evidence of
what a feed said, over a connection nobody vouched for. Left as-is per the owner's
"in if you cannot get them, ignore them".

## The faith pass, and `rabbit` matching `rabbi` (2026-11-06)

Product 36,067 unchanged in count, **184 tests**, `--strict` 0. `topic:religion`
1,682 → **1,802**, `topic:media`-only 1,655 → **1,536**.

The recommendation for the 1,655 media-only feeds was to *not* grind them, and the shape
measurement showed why the bounded version works: 797 of them signal a subject in their own
title or description (205 news-shaped, 202 tech, 128 faith, 65 home/hobby, 64 writing, 55
parenting), and **858 signal nothing at all** — for those `media` is currently the honest
answer. So the pass taken was the one the tool can already see: every media-only row whose
own text fires the *shipped* religion rule. **119 tagged**, one declined.

Selecting with the tool's own rule rather than a regex of my own was the right instinct and
it removed the false positives my first attempt had invented (Dutch `bespreken`/`gesprek` —
"discuss", "conversation" — matching `preken`, a sermon). It also caught a real defect:

**The religion rule carried `rabbi\w*` with no leading boundary, and the rules run under
`re.I`, so it matched `rabbit` — the entire word.** 21 shipped feeds have rabbit as their
only religion signal (Hundred Rabbits is a solar-powered-computers blog, "A RABBIT'S FOOT"
is an art blog); they survived only because the pile-up guard stops a rule adding a topic
to a feed that already has one. A *fresh candidate* would have been filed as religion, and
one such row — a substack literally called "rabbit holes" — was sitting in the first draft
of this pass when I read it by eye. Fixed to `\brabbis?\b|\brabbin(?:ic|ical)\b`; 3 tests,
and restoring `rabbi\w*` fails exactly the two rabbit ones.

Before `--apply`, checked the thing the invariant actually cares about: `topic:media` is
usually a placeholder, but **239 hand rules at HEAD do decide `media` deliberately** — so
the 119 were checked against all of them, and **none** of the 119 had a hand-decided
`media`. That check is also why "rabbit holes" keeps its media tag: a human wrote it
there, and the corrected rule no longer disagrees.
