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

Still open: **~650 verified feeds sit in `data/DISCOVERY_UNTAGGED.md`** because
nothing decides their tags. They are not merged and not dropped. Most are on
`feeds.feedburner.com` and `medium.com`, where the path names a different
publisher every time, so no site-level rule is true and each feed needs its own
line.

51 hand host rules were written for the batch (`discovery-decisions.txt`,
`discovery-decisions-2.txt`), and `TAGS.md` gained `region:italy`, `mexico`, 
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
python3 tools/decide.py discovery-decisions.txt
python3 tools/add.py merge data/candidates.tagged.jsonl   # then --apply
```
