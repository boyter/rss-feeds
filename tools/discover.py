"""Turn other people's curated lists into candidates. Nothing here is added.

The pipeline already verifies a candidate by fetching it (add.py probe) and only
admits a URL seen answering with a real feed. What was missing is a source of
candidates. This tool reads curated lists — Markdown READMEs and OPML files that
name feeds — and turns them into data/candidates.jsonl, deduped against
feeds.json with vocab.norm_key so "already present" is decided the same way
add.py and rebuild.py decide it.

Only `fetch` touches the network, and only for the handful of list URLs named in
the sources file. Everything after that parses text it was given. The feeds
themselves are fetched by add.py probe, under harvest.py's etiquette.

Usage:
    python3 discover.py fetch sources.txt        # -> data/sources/<slug>.md
    python3 discover.py extract                  # -> data/candidates.jsonl
    python3 discover.py paths                    # expand homepage candidates to feed paths
    python3 discover.py tag                      # -> data/candidates.tagged.jsonl

A sources line is a URL, optionally followed by a tab/comment naming the list:

    https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/README.md

`tag` runs after probe. It tags a candidate from what the probe *saw* — the
feed's own title, description and sample items, through classify.py's rules —
and only falls back to the list's own category heading when the evidence is
silent. The order is deliberate: a list written in 2015 filed a blog under
"Tech" because that was the heading available, while the feed's current title is
a fact about the feed today.
"""

import argparse
import collections
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import classify
import harvest
import paths
import vocab as vocab_mod

SOURCES = paths.data("sources.txt")
SRCDIR = paths.data("sources")
# Not data/candidates.jsonl: that file is committed and holds hand-proposed
# candidates with tags, i.e. human decisions. A generated list goes to its own
# file so a discovery run can never overwrite a decision.
CANDIDATES = paths.data("candidates.discovered.jsonl")
EXPANDED = paths.data("candidates.paths.jsonl")
RESULTS = paths.data("probe_results.jsonl")
TAGGED = paths.data("candidates.tagged.jsonl")
SIBLINGS = paths.data("candidates.siblings.jsonl")
LEADS = paths.data("candidates.leads.jsonl")
PAGES = paths.data("candidates.pages.jsonl")
ORACLE = paths.data("candidates.oracle.jsonl")
ORACLE_CACHE = paths.data("oracle.jsonl")

# feedsearch.dev keeps "the location and metadata of all crawled feeds" and
# answers a GET with no key, no signup and no rate-limit dance. It is a per-site
# oracle, not a keyword index: ask it about a host and it names that host's
# feeds, including ones that advertise themselves nowhere we can read.
ORACLE_URL = "https://origin.feedsearch.dev/api/v1/search"

# rssamplifier.com is an open directory (~200k blog feeds, 311k podcasts) whose
# robots.txt and skill.md name the entry points and prefer them to HTML crawling.
# /opml?topic=<subject> answers one subject as a subscription list, which is the
# shape the pipeline already eats: URLs, no claims about tags.
AMP_URL = "https://rssamplifier.com/opml"
AMP_ALL = paths.data("sources/rssamplifier.opml")
AMP = paths.data("candidates.amp.jsonl")
AMP_CACHE = paths.data("amp.jsonl")

# A URL that cannot be a feed. Not a judgement about the site — about whether
# this particular URL can ever answer with RSS. raw.githubusercontent.com is the
# one that bit in the pilot: a curated README linked its own OPML files, and an
# OPML file is XML that parses, so probe recorded it as a feed.
NON_FEED_HOSTS = re.compile(
    r"(^|\.)(github\.com|githubusercontent\.com|gitlab\.com|sourceforge\.net|"
    r"twitter\.com|x\.com|facebook\.com|instagram\.com|linkedin\.com|"
    r"play\.google\.com|apps\.apple\.com|wikipedia\.org|archive\.org|"
    r"web\.archive\.org|feedly\.com|inoreader\.com|bloglines\.com)$")
NON_FEED_PATH = re.compile(
    r"\.(opml|png|jpe?g|gif|svg|ico|css|js|pdf|zip|tar|gz|txt|json\.md|"
    r"md|html?|php|aspx?|jsp)(\?|$)", re.I)
# A feed path that hangs off an HTML page: /blog/archives/2025/01/post.html/feed.
# A feed index named 385 of these for schneier.com and every one of them 404s or
# 403s - the index is appending /feed to every page it crawled. Measured 0/385,
# which is why this is a rule and not a hunch: a real feed is never a child of a
# page. NON_FEED_PATH cannot see it, because that only checks the last segment.
# Deliberately html/htm only. WordPress serves real feeds at /index.php/feed/, so
# a script name in the path is not evidence of anything, and cutting .php would
# delete a live pattern to stop a dead one.
FEED_UNDER_A_PAGE = re.compile(r"/[^/]*\.html?/", re.I)
# A URL with no path is a homepage: it is a lead, not a feed. `paths` turns it
# into the handful of locations a feed is usually at on that engine.
HOMEPAGE_PATH = re.compile(r"^/?$")
COMMON_FEED_PATHS = ("feed/", "index.xml", "feed.xml", "atom.xml", "rss.xml",
                     "rss/", "feed", "feeds/posts/default", "feed/json")

URL_RE = re.compile(r"https?://[^\s<>\)\]\"'`]+")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")

# A list's own heading -> tags. High precision, same discipline as
# classify.TOPIC_RULES: a heading that fires on the wrong feed does not get
# reviewed, because it looked like the list said so. Only used when the feed's
# own evidence is silent.
CATEGORY_TOPICS = [
    (r"security|infosec|cyber|privacy|hacking|malware|threat", ["topic:security"]),
    (r"\bmachine learning\b|\bai\b|artificial intelligence|data science|\bml\b", ["topic:ai"]),
    (r"data\b|database|analytics|big data", ["topic:data"]),
    (r"devops|infrastructure|cloud|sysadmin|sysadmin|sre", ["topic:infrastructure"]),
    (r"front[- ]?end|web dev|javascript|\bcss\b|\bhtml\b|webdesign|web design", ["topic:web-development"]),
    (r"linux|unix|operating system|freebsd|openbsd|kernel", ["topic:systems"]),
    (r"network|wifi|tcp/ip", ["topic:networking"]),
    (r"hardware|retro|arduino|raspberry", ["topic:hardware"]),
    (r"open source|free software|\bfoss\b", ["topic:open-source"]),
    (r"startup|business|entrepreneur|marketing|saas", ["topic:business"]),
    (r"android develop|ios develop|mobile develop|mobile app develop|app develop", ["topic:software-engineering"]),
    (r"gadgets?|smartphone|apple|iphone|tablet|reviews?", ["topic:gadgets"]),
    (r"game|gaming|xbox|playstation|nintendo", ["topic:gaming"]),
    (r"science|space|physics|biology|nature", ["topic:science"]),
    (r"math|statistics", ["topic:mathematics"]),
    (r"politic|election|world news|current affairs", ["topic:politics"]),
    (r"finance|money|invest|stock|econom", ["topic:finance"]),
    (r"sport|football|soccer|cricket|nba|nfl", ["topic:sport"]),
    (r"music|audio", ["topic:music"]),
    (r"movie|film|tv|television|entertain", ["topic:entertainment"]),
    (r"design|ux|typograph|art\b", ["topic:design"]),
    (r"photograph", ["topic:design"]),
    (r"book|literature|reading", ["topic:books"]),
    (r"health|medical|medicine|fitness", ["topic:health"]),
    (r"travel", ["topic:travel"]),
    (r"food|recipe|cooking", ["topic:food"]),
    (r"educat|learn|teach|student|university|college", ["topic:education"]),
    (r"news|newspaper|press|media|journalis", ["topic:news"]),
    (r"programming|coding|software develop|developer|tech\b|technology|engineering",
     ["topic:software-engineering"]),
    (r"podcast", ["topic:media"]),
    (r"environment|climate|energy", ["topic:environment"]),
    (r"history", ["topic:history"]),
    (r"philosophy", ["topic:philosophy"]),
    (r"religio", ["topic:religion"]),
    (r"lifestyle|parenting|family|home", ["topic:lifestyle"]),
]

# The heading also says what kind of source the list thinks these are. Used only
# as the last resort, because `type:` is required and a feed with no title gives
# the rules nothing to work with.
CATEGORY_TYPES = [
    (r"podcast", "type:podcast"),
    (r"newsletter|mailing list|substack", "type:newsletter"),
    (r"news|newspaper|press|media|journalis|magazine|site|aggregat", "type:publication"),
    (r"personal|blog|blogs|individual|indie|microblog", "type:personal-blog"),
    (r"compan|vendor|corporate|product|engineering blog", "type:vendor-blog"),
    (r"university|edu|gov|research|institute", "type:institution"),
    (r"reddit|forum|community|stackexchange|news aggregat", "type:community"),
    (r"video|youtube", "type:video"),
]


def host_of(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def slug(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def cmd_fetch(args):
    if not os.path.exists(SOURCES):
        print(f"no {SOURCES}", file=sys.stderr)
        return 1
    os.makedirs(SRCDIR, exist_ok=True)
    urls = [l.split("#")[0].strip() for l in open(SOURCES, encoding="utf-8")]
    urls = [u for u in urls if u]
    for u in urls:
        dest = os.path.join(SRCDIR, slug(u) + ".txt")
        if os.path.exists(dest) and not args.restart:
            print(f"  have  {u[:70]}")
            continue
        req = urllib.request.Request(u, headers=harvest.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(2_000_000)
                ce = r.headers.get("Content-Encoding", "")
        except Exception as e:
            print(f"  FAIL  {u[:70]} {type(e).__name__}: {e}")
            continue
        # The shared headers advertise gzip, so the list arrives compressed. The
        # same trap as the feed bodies: undecoded bytes parse as nothing, and an
        # empty list looks like an empty source rather than a failed fetch.
        kind, _ = harvest.decompressor_for(ce, body[:4])
        if kind == "gzip":
            text = harvest.decode(body, ce)
            if text.startswith("[undecodable"):
                print(f"  FAIL  {u[:70]} {text}")
                continue
            body = text.encode("utf-8")
        with open(dest, "wb") as fh:
            fh.write(body)
        print(f"  got   {u[:70]} ({len(body)} bytes)")
    return 0


def clean_url(u):
    u = html.unescape(u).strip().rstrip(".,;:'\"!?")
    # A markdown link written by hand often keeps an anchor; a feed URL with a
    # fragment is the same feed, and the fragment is not part of the request.
    u = u.split("#", 1)[0]
    return u


# Links a page declares that are not feeds worth carrying. A WordPress comment
# feed is real RSS, but it is the site's comment traffic, not its content, and a
# Google or Microsoft News mirror is someone else's aggregator of a publisher we
# already list. Both were found in bulk by the sibling pass, so both are named
# here and counted, never quietly dropped.
NOT_WORTH_CARRYING = re.compile(
    r"(^|/)(comments/feed|feed/comments|comments/rss)(/|$|\?)", re.I)
MIRROR_HOSTS = re.compile(
    r"(^|\.)(news\.google\.|go\.redirectingat\.|msn\.com|news\.microsoft\.|"
    r"news\.yahoo\.|bing\.com|feedburner\.google\.com)$")


def worth_carrying(url):
    p = urlparse(url)
    if NOT_WORTH_CARRYING.search(p.path):
        return False, "comment feed"
    if MIRROR_HOSTS.search(p.netloc.lower().removeprefix("www.")):
        return False, "news mirror"
    return True, ""


def is_plausible_feed(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False, "scheme"
    host = p.netloc.lower().removeprefix("www.")
    if "." not in host:
        return False, "no tld"
    if NON_FEED_HOSTS.search(host):
        return False, "host"
    if NON_FEED_PATH.search(p.path):
        return False, "path"
    if FEED_UNDER_A_PAGE.search(p.path):
        return False, "feed under a page"
    return True, ""


def iter_source_text(path):
    """Yield (url, category) pairs from one fetched list.

    Markdown: the nearest preceding heading is the category.
    OPML: the enclosing outline's text/title is the category, xmlUrl is the feed.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    if "<opml" in text[:2000].lower():
        yield from iter_opml(text)
        return
    heading = ""
    for line in text.splitlines():
        h = re.match(r"^#{1,6}\s+(.*)$", line.strip())
        if h:
            heading = h.group(1).strip()
            continue
        for m in MD_LINK_RE.finditer(line):
            yield m.group(2), heading
        # Bare URLs, e.g. an OPML-ish list or a plain-text list. This used to be
        # gated on the line having no square bracket, which silently lost every
        # bare URL sharing a line with a markdown link: a lead that reached no
        # candidates file and no counter, so the run reported its totals as if it
        # had never been named. Yield them all, skipping only the exact string the
        # markdown link already yielded, or each linked feed is seen twice.
        linked = {m.group(2) for m in MD_LINK_RE.finditer(line)}
        for m in URL_RE.finditer(line):
            if m.group(0) not in linked:
                yield m.group(0), heading


def iter_opml(text):
    """(feed url, category path) from an OPML body.

    ElementTree first, because a line-based scan silently yields nothing for an
    OPML file written on one line - which parses as an empty list, so the run
    reports zero candidates and looks like an empty source rather than a broken
    parser. Malformed OPML is common enough that a regex fallback follows, and
    both paths report through the caller's counters.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        for m in re.finditer(r'<outline\b[^>]*?xmlUrl\s*=\s*["\']([^"\']+)["\'][^>]*>',
                             text, re.I):
            yield m.group(1).strip(), ""
        return

    def walk(node, stack):
        label = (node.get("text") or node.get("title") or "").strip()
        xml = (node.get("xmlUrl") or "").strip()
        if xml:
            # The enclosing outlines only. The outline's own text is the feed's
            # name, and feeding a feed's name to the category rules is how
            # "Apple Weekly" becomes topic:gadgets by accident.
            yield xml, " / ".join(stack)
        child_stack = stack + ([label] if label and not xml else [])
        for child in node:
            if child.tag == "outline":
                yield from walk(child, child_stack)

    body = root.find("body")
    if body is None:
        return
    yield from walk(body, [])


def category_tags(cat, voc):
    topics, ctype = [], None
    low = cat.lower()
    for pattern, tags in CATEGORY_TOPICS:
        if re.search(pattern, low):
            topics.extend(t for t in tags if t in voc and t not in topics)
    for pattern, t in CATEGORY_TYPES:
        if re.search(pattern, low):
            ctype = t
            break
    return topics, ctype


def cmd_extract(args):
    voc = vocab_mod.load()
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    have = {vocab_mod.norm_key(f["url"]) for f in feeds}
    if not os.path.isdir(SRCDIR):
        print(f"no {SRCDIR}; run fetch first", file=sys.stderr)
        return 1

    rows, seen = [], set()
    stats = collections.Counter()
    for name in sorted(os.listdir(SRCDIR)):
        src = os.path.join(SRCDIR, name)
        if not os.path.isfile(src):
            continue
        for raw, cat in iter_source_text(src):
            stats["seen"] += 1
            url = clean_url(raw)
            ok, why = is_plausible_feed(url)
            if not ok:
                stats["dropped:" + why] += 1
                continue
            key = vocab_mod.norm_key(url)
            if key in have:
                stats["dropped:already in feeds.json"] += 1
                continue
            if key in seen:
                stats["dropped:duplicate in batch"] += 1
                continue
            seen.add(key)
            topics, ctype = category_tags(cat, voc)
            rows.append({"url": url, "tags": [], "source": name,
                         "category": cat[:80], "hintTopics": topics,
                         "hintType": ctype})
    if args.limit:
        rows = rows[:args.limit]
    with open(CANDIDATES, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} candidates -> {CANDIDATES}")
    for k, v in sorted(stats.items()):
        print(f"  {k:36} {v}")
    print("  categories seen:")
    cc = collections.Counter(r["category"] for r in rows)
    for cat, n in cc.most_common(15):
        print(f"    {n:5} {cat}")
    return 0


def is_homepage(url):
    """True when the URL names a site, not a feed - so it is a lead to expand.

    Only a bare homepage (or a bare /blog) qualifies. "/feed/" ends in a slash
    like a homepage does, but the list already named a feed there: expanding it
    would probe seven paths for a URL we were given.
    """
    path = urlparse(url).path
    return bool(HOMEPAGE_PATH.match(path)) or path.lower().rstrip("/") == "/blog"


def cmd_paths(args):
    """Expand homepage candidates into the paths a feed usually sits at.

    A curated list that names only `https://example.com/` is a lead, not a feed;
    the invariant still has to be satisfied by a probe. Only bare homepages are
    expanded, so the batch stays bounded.
    """
    rows = read_jsonl(CANDIDATES)
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    have = {vocab_mod.norm_key(f["url"]) for f in feeds}
    out, n, dup = [], 0, 0
    for r in rows:
        p = urlparse(r["url"])
        if not is_homepage(r["url"]):
            continue
        base = f"{p.scheme}://{p.netloc}/"
        for cp in COMMON_FEED_PATHS:
            url = base + cp
            if vocab_mod.norm_key(url) in have:
                dup += 1
                continue
            out.append({**r, "url": url, "via": "common-path"})
        n += 1
    with open(EXPANDED, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{n} homepage candidates -> {len(out)} probes ({dup} already in feeds.json) -> {EXPANDED}")
    return 0


# Hosts and title shapes that state what kind of source the feed is. Narrow on
# purpose, and every feed they decide for is reported: type: is the one facet a
# later host rule is allowed to replace (see merge_tags), so a wrong guess here
# is recoverable in a way a wrong topic is not - but it is still a guess.
PODCAST_HOSTS = re.compile(
    r"(relay\.fm|feeds\.twit\.tv|podcasts\.files\.bbci\.co\.uk|"
    r"feeds\.megaphone\.fm|omny\.fm|simplecast\.com|buzzsprout\.com|"
    r"libsyn\.com|podbean\.com|feeds\.soundcloud\.com|rss\.spreaker\.com)$")
TYPE_HINTS = [
    # "All About Android (Audio)" is a TWiT episode feed; the parenthetical is
    # how that family labels itself.
    (re.compile(r"\((audio|video)\)", re.I), "type:podcast"),
    (re.compile(r"^stories by .+ on medium$", re.I), "type:personal-blog"),
    (re.compile(r"\b(engineering|technology|research)\b.*\bblog\b", re.I),
     "type:vendor-blog"),
    (re.compile(r"\b(news agency|newsdesk|press release)\b", re.I), "type:publication"),
]


def type_hint(url, title):
    if PODCAST_HOSTS.search(host_of(url)):
        return "type:podcast"
    for pattern, tag in TYPE_HINTS:
        if pattern.search(title or ""):
            return tag
    return None


# On an aggregator host the items are other people's content: a YouTube channel's
# six most recent video titles say nothing reliable about the channel, and this
# is the same failure classify.py was called out for - one headline mentioning AI
# put topic:ai on 273 feeds. So on these hosts a curated category outranks the
# item rules, and the swap is reported like any other hint.
AGGREGATOR_HOSTS = re.compile(r"(youtube\.com|(feeds2?\.)?feedburner\.com|reddit\.com)$")


def aggregator_host(url):
    return bool(AGGREGATOR_HOSTS.search(host_of(url)))


def load_overrides():
    """The host rules a human already made, keyed by host.

    A new candidate on a host the project already decided for inherits that
    decision - which is the same reasoning as pathTags in classify.py, and the
    only honest way to tag a category feed of a site whose type is settled. A
    host rule may settle `type:`; it may not supply the whole answer, because a
    host rule that erases a topic is the npr.org defect (see merge_tags).
    """
    rules = {}
    for r in read_jsonl(paths.data("overrides.jsonl")):
        key = r["key"].lower()
        if "/" in key:
            continue
        rules[key.removeprefix("www.")] = r
    return rules


def override_for(url, rules):
    return rules.get(host_of(url))


def load_url_overrides():
    """The per-feed rules a human already made, keyed by norm_key.

    discover.py writes these for proxy hosts (feeds.feedburner.com, medium.com),
    where the path names a different publisher every time and no site-level rule
    is true. Without this lookup those rules are written and then never applied:
    the queue's last 116 rows were exactly that.
    """
    rules = {}
    for r in read_jsonl(paths.data("overrides.jsonl")):
        key = r["key"]
        if "/" not in key or "://" not in key:
            continue
        rules[vocab_mod.norm_key(key)] = r
    return rules


def cmd_tag(args):
    """Tag probed candidates from what the feed itself said."""
    voc = vocab_mod.load()
    classify.VOCAB = voc
    cands = (read_jsonl(CANDIDATES) + read_jsonl(EXPANDED) + read_jsonl(LEADS)
             # Oracle leads, not the pages they were asked about: PAGES and
             # SIBLINGS hold homepages, and a homepage is never a candidate feed.
             + read_jsonl(ORACLE) + read_jsonl(AMP))
    probed = {r["url"]: r for r in read_jsonl(RESULTS)}
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    have = {vocab_mod.norm_key(f["url"]) for f in feeds}

    rows, seen, stats = [], set(), collections.Counter()
    untagged = []
    rules = load_overrides()
    url_rules = load_url_overrides()
    for c in cands:
        r = probed.get(c["url"])
        if not r:
            stats["not probed"] += 1
            continue
        if not r.get("isFeed"):
            stats["not a feed"] += 1
            continue
        key = vocab_mod.norm_key(c["url"])
        if key in have or key in seen:
            stats["duplicate"] += 1
            continue
        ok, why = worth_carrying(c["url"])
        if not ok:
            stats["dropped: " + why] += 1
            continue
        seen.add(key)
        # A channel that found the URL under a heading carries that heading in
        # `category`. Reading it here, in one place, keeps a curated list, a
        # subject query and the whole directory on the same rule instead of three
        # slightly different ones - and the aggregator gate further down still
        # refuses to inherit a topic onto youtube/feedburner/medium paths, because
        # there the heading belongs to whoever made the list, not to the publisher.
        if not c.get("hintTopics") and c.get("category"):
            c["hintTopics"], c["hintType"] = category_tags(c["category"], voc)
        rec = {k: r.get(k) for k in ("url", "title", "description", "items")}
        rec["url"] = c["url"]
        rule_tags, why = classify.suggest(rec, [])
        # A candidate is about to be pinned forever, so the only text allowed to
        # decide its topics is the feed's own name and description. classify's
        # haystack also holds six recent headlines, and that is what put
        # topic:software-engineering on Defense News' Land feed and topic:food on
        # WSJ Markets - one headline mentioning a thing is not what a feed is
        # about. Types, region and language still read the full haystack: a
        # Cyrillic headline is evidence of language in a way a headline is not
        # evidence of topic.
        name_tags, _ = classify.suggest({**rec, "items": []}, [])
        topics = [t for t in name_tags if t.startswith("topic:")][:2]
        types = [t for t in rule_tags if t.startswith("type:")]
        origin = []
        exact = url_rules.get(vocab_mod.norm_key(c["url"]))
        if exact:
            # A human named this exact feed. That is the most specific decision
            # there is - more specific than the feed's own title - and merge_tags
            # treats a URL rule as the whole answer for the facets it names.
            topics = [t for t in exact["tags"] if t.startswith("topic:")]
            got = [t for t in exact["tags"] if t.startswith("type:")]
            if got:
                types = got[:1]
            if topics:
                origin.append("url rule")
            if types:
                origin.append("url rule")
        if not topics and aggregator_host(c["url"]) and c.get("hintTopics"):
            # A human filed this channel under a heading; for an aggregator that
            # beats the channel's own recent headlines.
            topics = c["hintTopics"][:2]
            origin.append("category over items")
        # Weakest last. A human's host rule outranks a curated list's heading,
        # and both are only consulted when the feed's own title said nothing.
        if not types:
            hint = type_hint(c["url"], r.get("title", ""))
            if hint:
                types = [hint]
                origin.append("type pattern")
        rule = override_for(c["url"], rules)
        if rule:
            for needle, tags_extra in (rule.get("pathTags") or {}).items():
                if needle.lower() in c["url"].lower():
                    extra = [t for t in tags_extra if t.startswith("topic:")]
                    if not topics and extra:
                        topics = extra[:2]
                        origin.append("host pathTags")
            if not types:
                got = [t for t in (rule.get("tags") or []) if t.startswith("type:")]
                if got:
                    types = got[:1]
                    origin.append("host rule")
            if not topics and not aggregator_host(c["url"]):
                # A host rule's own tags describe the site, so on a site they are
                # evidence about every feed it publishes. On an aggregator each
                # path is a different publisher and they are nothing of the sort:
                # youtube.com carries topic:science, which made Bon Appétit and
                # Bloomberg Originals science channels. merge_tags keeps the
                # stricter rule for feeds already in the list - a host rule may
                # never *replace* a topic there - and this is the additive side.
                got = [t for t in (rule.get("tags") or []) if t.startswith("topic:")]
                if got:
                    topics = got[:2]
                    origin.append("host rule")
            # A host rule's own tags may settle type: and nothing else. They
            # describe the site, and merge_tags already says a host rule must not
            # decide a topic: the npr.org rule once stripped topic:health from the
            # Global Health feed. Read the other way, youtube.com's host rule
            # carries topic:science, which would have made Bon Appétit and
            # Bloomberg Originals science channels. pathTags are per path, so
            # they may bring a topic.
        if not topics and c.get("hostTags") and not aggregator_host(c["url"]):
            # A human already decided these tags for another feed on this host -
            # which is a real signal for a category feed of a newspaper, and
            # meaningless on an aggregator, where every path is a different
            # publisher. Without the gate, one channel's topic is copied onto
            # every new channel on the host: the youtube.com/Bon Appétit failure
            # again, arriving through the sibling door instead of the host rule.
            got = [t for t in c["hostTags"] if t.startswith("topic:")]
            if got:
                topics = got[:2]
                origin.append("sibling feed")
        if not types and c.get("hostTags"):
            got = [t for t in c["hostTags"] if t.startswith("type:")]
            if got:
                types = got[:1]
                origin.append("sibling feed")
        if not topics and c.get("hintTopics"):
            topics = c["hintTopics"][:2]
            origin.append("category")
        if not types and c.get("hintType"):
            types = [c["hintType"]]
            origin.append("category")
        tags = [t for t in rule_tags if not t.startswith(("topic:", "type:"))]
        tags = topics + types + tags
        bad = vocab_mod.validate(tags, voc)
        if bad:
            stats["bad tags"] += 1
            continue
        if not topics or not types:
            stats["still untagged (needs a human)"] += 1
            untagged.append({"url": c["url"], "title": r.get("title", ""),
                             "description": r.get("description", ""),
                             "category": c.get("category", ""),
                             "missing": (("topic" if not topics else "") +
                                         ("+type" if not types else "")).lstrip("+")})
            continue
        # A topic supplied by the list's heading rather than by the feed's own
        # title is a guess, and merge pins it: a tag already in feeds.json
        # outranks a rule's guess forever, so a wrong one written here is never
        # revisited. The heading is still the best evidence there is when the
        # feed says nothing, so it is used - but every feed it decided for is
        # written out for a human to veto before the merge, never absorbed.
        rows.append({"url": c["url"], "tags": vocab_mod.normalize(tags),
                     "title": r.get("title", ""), "tagWhy": why,
                     "tagOrigin": origin, "category": c.get("category", ""),
                     "source": c.get("source", "")})
        stats["tagged"] += 1
    with open(TAGGED, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_hint_report(rows)
    write_untagged_report(untagged)
    print(f"{len(rows)} feed-backed candidates -> {TAGGED}")
    for k, v in sorted(stats.items()):
        print(f"  {k:34} {v}")
    print(f"  {sum(1 for r in rows if r['tagOrigin'])} tagged from a list heading "
          f"-> data/DISCOVERY_REVIEW.md (read before merging)")
    return 0


def write_hint_report(rows):
    """List the candidates whose tags rest on something other than the feed.

    Reported, never silently kept: merge.py pins what it writes, so a heading or
    a sibling's tag that was wrong for this feed would otherwise be permanent.
    """
    hinted = sorted((r for r in rows if r["tagOrigin"]),
                    key=lambda r: (tuple(r["tagOrigin"]), r["category"], r["url"]))
    with open(paths.data("DISCOVERY_REVIEW.md"), "w", encoding="utf-8") as fh:
        fh.write("# Tags not taken from the feed itself\n\n"
                 "A topic or type below came from a host rule, from a sibling feed "
                 "on the same host, or from the category a curated list filed the "
                 "URL under - not from this feed's own title and items. merge.py "
                 "pins what it writes, so read this before merging and fix "
                 "anything wrong with decide.py.\n\n")
        fh.write("| origin | url | title | list category | tags |\n"
                 "|---|---|---|---|---|\n")
        for r in hinted:
            fh.write(f"| {'+'.join(r['tagOrigin'])} | {cell(r['url'], 90)} "
                     f"| {cell(r['title'], 60)} | {cell(r['category'], 24)} "
                     f"| {' '.join(r['tags'])} |\n")


def cell(text, limit=70):
    """One table cell. A title or description containing a pipe would otherwise
    shift every later column, and the queue is read by a person."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()[:limit]


def write_untagged_report(untagged):
    """Feeds that answered as feeds but that no rule and no hint can tag.

    They are not merged and not dropped: they are a queue. The fix is a host rule
    written with decide.py, which covers every feed on the site at once.
    """
    untagged.sort(key=lambda r: (host_of(r["url"]), r["url"]))
    # The Markdown table is for a person; the JSONL is so the next pass does not
    # have to parse a table whose cells can contain anything a feed's title
    # contains.
    with open(paths.data("DISCOVERY_UNTAGGED.jsonl"), "w", encoding="utf-8") as fh:
        for r in untagged:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(paths.data("DISCOVERY_UNTAGGED.md"), "w", encoding="utf-8") as fh:
        fh.write("# Candidates that are feeds but have no decidable tags\n\n"
                 "Each of these answered with a real feed, so it is verified; "
                 "none is merged, because merge requires a topic and exactly one "
                 "type and nothing here supplies them. To admit one, write a "
                 "host rule with tools/decide.py - one line covers every feed on "
                 "the host - then re-run discover.py tag.\n\n"
                 "| host | url | title | description | list category | missing |\n"
                 "|---|---|---|---|---|---|\n")
        for r in untagged:
            fh.write(f"| {cell(host_of(r['url']), 40)} | {cell(r['url'], 90)} "
                     f"| {cell(r['title'], 60)} | {cell(r['description'])} "
                     f"| {cell(r['category'], 24)} | {r['missing']} |\n")


def cmd_siblings(args):
    """Propose the homepages of hosts that contribute exactly one feed.

    2,049 hosts and only 97 of them carry more than one feed, so the category,
    tag and comment feeds of sites we already vetted are the cheapest uncollected
    feeds in the project. harvest.probe already records an HTML page's feed links
    in altFeed without calling the page a feed, so the probe step needs no new
    code and the invariant is untouched: a homepage is never a candidate feed,
    only a place to look.
    """
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    by_host = collections.defaultdict(list)
    for f in feeds:
        by_host[host_of(f["url"])].append(f["url"])
    rows = []
    for host, urls in sorted(by_host.items()):
        if len(urls) > args.max_per_host:
            continue
        p = urlparse(urls[0])
        rows.append({"url": f"{p.scheme}://{p.netloc}/", "tags": [],
                     "source": "sibling-homepage", "category": "",
                     "hintTopics": [], "hintType": None, "via": "sibling",
                     "hostTags": sorted({t for u in urls for t in tags_of(u, feeds)})})
    with open(SIBLINGS, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} single-feed homepages -> {SIBLINGS}")
    return 0


def tags_of(url, feeds):
    key = vocab_mod.norm_key(url)
    for f in feeds:
        if vocab_mod.norm_key(f["url"]) == key:
            return f.get("tags", [])
    return []


def cmd_leads(args):
    """Turn probe records' altFeed entries into candidates.

    The lead was found by fetching a page we already trust, so the host's own
    tags come with it - but they arrive as hints, not tags, because a category
    feed of a site is not the same feed as the site's front page.
    """
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    have = {vocab_mod.norm_key(f["url"]) for f in feeds}
    probed = read_jsonl(RESULTS)
    by_host = collections.defaultdict(list)
    for f in feeds:
        by_host[host_of(f["url"])].append(f["url"])
    rows, stats = [], collections.Counter()
    for r in probed:
        for lead in r.get("altFeed", []):
            stats["altFeed seen"] += 1
            lead = clean_url(lead)
            ok, why = is_plausible_feed(lead)
            if not ok:
                stats["dropped:" + why] += 1
                continue
            ok, why = worth_carrying(lead)
            if not ok:
                stats["dropped:" + why] += 1
                continue
            key = vocab_mod.norm_key(lead)
            if key in have:
                stats["dropped:already in feeds.json"] += 1
                continue
            if key in {vocab_mod.norm_key(x["url"]) for x in rows}:
                stats["dropped:duplicate in batch"] += 1
                continue
            rows.append({"url": lead, "tags": [], "source": "altFeed",
                         "category": "", "hintTopics": [], "hintType": None,
                         "via": "altFeed", "foundOn": r["url"],
                         # The page it was found on is a feed we already carry, so
                         # the tags a human gave that feed are the best evidence
                         # about its sibling - they arrive as hints, because a
                         # category feed is not the same feed as the front page.
                         "hostTags": sorted({t for u in by_host.get(host_of(r["url"]), [])
                                             for t in tags_of(u, feeds)})})
    with open(LEADS, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} feed links found on pages we already trust -> {LEADS}")
    for k, v in sorted(stats.items()):
        print(f"  {k:36} {v}")
    return 0


def cmd_pages(args):
    """Turn a named list of sites into probe targets, so they can be asked for feeds.

    Guessing `/feed` and `/rss.xml` on sites nobody recommended measured 3,754
    HTML pages against 23 real feeds, and a guessed path that 404s teaches
    nothing about a site that serves its feed at `/blog/atom.xml`. A page answers
    that question directly: harvest.probe records an HTML page's feed links in
    altFeed without calling the page a feed, and `leads` turns those into
    candidates. So this writes homepages, never feeds, and never fetches.
    """
    rows, stats = [], collections.Counter()
    for line in open(args.sites, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            line = json.loads(line).get("url", "")
        if not line.lower().startswith(("http://", "https://")):
            stats["dropped:not a URL"] += 1
            continue
        p = urlparse(line)
        home = f"{p.scheme}://{p.netloc}/"
        if home in {r["url"] for r in rows}:
            stats["dropped:duplicate"] += 1
            continue
        rows.append({"url": home, "tags": [], "source": "named-site",
                     "category": "", "hintTopics": [], "hintType": None,
                     "via": "named-site"})
    with open(PAGES, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} sites to ask for their feeds -> {PAGES}")
    for k, v in sorted(stats.items()):
        print(f"  {k:30} {v}")
    return 0


def oracle_query(site, skip_crawl=True):
    """Ask feedsearch.dev which feeds a site has. Returns (feeds, error).

    skip_crawl defaults to True: the saved index answers the question we ask, and
    asking it to crawl means a third party fetching a stranger's site on our
    behalf, which is not our crawl to order.

    The shared headers advertise gzip, so the index answers compressed and urllib
    does not undo that - gzipped bytes are not JSON, which is the same trap as the
    feed bodies, where a compressed answer used to look like an empty one.
    """
    q = urllib.parse.urlencode({"url": site, "info": "true", "favicon": "false",
                                "skip_crawl": "true" if skip_crawl else "false"})
    req = urllib.request.Request(ORACLE_URL + "?" + q, headers=harvest.HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read(4_000_000)
            ce = r.headers.get("Content-Encoding", "")
        text = harvest.decode(raw, ce)
        if text.startswith("[undecodable"):
            return [], text
        payload = json.loads(text)
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"
    if isinstance(payload, dict) and payload.get("error"):
        return [], payload.get("message") or payload["error"]
    rows = payload if isinstance(payload, list) else (payload.get("feeds") or [])
    out = []
    for x in rows:
        if isinstance(x, dict) and x.get("url"):
            out.append({"url": x["url"], "title": (x.get("title") or "")[:120]})
    return out, ""


def cmd_oracle(args):
    """Ask a feed index what feeds a known site has, and write them as leads.

    This is the repair channel: 3,273 hosts and 2,388 of them contribute exactly
    one feed, and a site's section, category and archive feeds advertise
    themselves in ways our harvester cannot see (JS-walled pages, a WAF that
    reads the TLS handshake). The index is a *claim about* a feed, never a feed:
    every line written here still has to be fetched by add.py probe before it can
    reach feeds.json, and the title the index reports is kept as a hint, not as
    the title, because the harvest is what reads a body.

    Answers are cached in data/oracle.jsonl, so a re-run does not re-ask - both
    politeness and the only way to tell "the index changed" from "we changed".

    Queries are one-at-a-time with a pause. This is someone's free service, not an
    elastic backend, and nothing here is urgent.

    --max-leads-per-site is the editorial cap, and it is in the tool rather than
    in a spreadsheet because the measured shape demands it: a random sample of 40
    of our own single-feed hosts gave 314 new live feeds sitting on 16 hosts, 257
    of them one Iranian newspaper's desks. Kept per site: shallowest path first,
    because /feed and /category/tech/feed are the feeds a reader wants and
    /category/a/b/c/d/feed is the index being exhaustive on our behalf.
    """
    cache = {r.get("site"): r for r in read_jsonl(ORACLE_CACHE)}
    rows, stats = [], collections.Counter()
    with open(ORACLE_CACHE, "a", encoding="utf-8") as cachefh:
        for site in oracle_sites(args):
            if site in cache and not args.restart:
                found, err = cache[site].get("feeds", []), cache[site].get("error", "")
                stats["cached"] += 1
            else:
                found, err = oracle_query(site, skip_crawl=not args.crawl)
                stats["queried"] += 1
                cachefh.write(json.dumps({"site": site, "feeds": found,
                                          "error": err}, ensure_ascii=False) + "\n")
                cachefh.flush()
            if err:
                stats["oracle error"] += 1
                print(f"  FAIL  {site[:44]:44} {err[:44]}")
                continue
            if not found:
                stats["index knows none"] += 1
                continue
            for f in found:
                lead = clean_url(f["url"])
                ok, why = is_plausible_feed(lead)
                if not ok:
                    stats["dropped:" + why] += 1
                    continue
                ok, why = worth_carrying(lead)
                if not ok:
                    stats["dropped:" + why] += 1
                    continue
                rows.append({"url": lead, "tags": [], "source": "feedsearch",
                             "category": "", "hintTopics": [], "hintType": None,
                             "via": "oracle", "oracleTitle": f.get("title", ""),
                             "aboutSite": site})
            stats["feeds named"] += len(found)
            time.sleep(args.pause)
        # Deduplicate on the one key the project agrees about.
        seen, out = set(), []
        for r in rows:
            k = vocab_mod.norm_key(r["url"])
            if k in seen:
                stats["dropped:duplicate in batch"] += 1
                continue
            seen.add(k)
            out.append(r)
        # The editorial cap, applied after dedup so what survives is chosen rather
        # than whatever the index happened to answer first.
        by_site = collections.defaultdict(list)
        for r in out:
            by_site[r["aboutSite"]].append(r)
        kept = []
        for site, rs in by_site.items():
            rs.sort(key=lambda r: (r["url"].count("/"), r["url"]))
            if len(rs) > args.max_leads_per_site:
                stats["dropped:per-site cap"] += len(rs) - args.max_leads_per_site
            kept.extend(rs[:args.max_leads_per_site])
        kept.sort(key=lambda r: r["url"])
    with open(ORACLE, "w", encoding="utf-8") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(kept)} feeds named by the index -> {ORACLE}")
    for k, v in sorted(stats.items()):
        print(f"  {k:30} {v}")
    return 0


def oracle_sites(args):
    """The sites to ask: a named file, or our own hosts, biggest gap first."""
    if args.sites:
        for line in open(args.sites, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line.startswith("{"):
                line = json.loads(line).get("url", "")
            if line:
                yield line
        return
    feeds = json.load(open(paths.root("feeds.json"), encoding="utf-8"))
    by_host = collections.defaultdict(list)
    for f in feeds:
        by_host[host_of(f["url"])].append(f["url"])
    # Single-feed hosts are where a site's other feeds are hiding.
    for host in sorted(by_host, key=lambda h: (len(by_host[h]), h)):
        if len(by_host[host]) > args.max_per_host:
            continue
        yield f"{host}"


def cmd_amp(args):
    """Ask a public blog directory for the feeds on a subject.

    This is the channel the oracle cannot be: it searches by topic, so it reaches
    hosts we have never heard of, which is the only breadth left. The directory's
    subject heading is kept as `category`, which the tagger treats as a hint and
    never as a tag - the security list that carried The Oatmeal is why.

    Gentle by construction: one subject at a time, a pause, answers cached in
    data/amp.jsonl so a re-run does not re-ask, and a per-subject cap, because a
    directory this deep will name 400 feeds for "nursing" and 400 near-clones of
    one publisher is not what a reader browses.
    """
    cache = {r.get("query"): r for r in read_jsonl(AMP_CACHE)}
    rows, stats = [], collections.Counter()
    if args.all:
        rows, stats = amp_all(args.limit, args.max_per_host)
        seen, out2 = set(), []
        for r in rows:
            k = vocab_mod.norm_key(r["url"])
            if k in seen:
                stats["dropped:duplicate in batch"] += 1
                continue
            seen.add(k)
            out2.append(r)
        with open(AMP, "w", encoding="utf-8") as fh:
            for r in out2:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{len(out2)} feeds named by the directory -> {AMP}")
        for k, v in sorted(stats.items()):
            print(f"  {k:32} {v}")
        return 0
    with open(AMP_CACHE, "a", encoding="utf-8") as cachefh:
        for q in read_queries(args.queries):
            if q in cache and not args.restart:
                found = cache[q].get("feeds", [])
                stats["cached"] += 1
            else:
                found = amp_topic(q)
                stats["queried"] += 1
                cachefh.write(json.dumps({"query": q, "feeds": found},
                                         ensure_ascii=False) + "\n")
                cachefh.flush()
                time.sleep(args.pause)
            if not found:
                stats["directory knows none"] += 1
                continue
            found.sort(key=lambda f: (urlparse(f["url"]).netloc.lower(), f["url"]))
            if len(found) > args.max_per_query:
                stats["dropped:per-query cap"] += len(found) - args.max_per_query
            for f in found[:args.max_per_query]:
                lead = clean_url(f["url"])
                ok, why = is_plausible_feed(lead)
                if not ok:
                    stats["dropped:" + why] += 1
                    continue
                ok, why = worth_carrying(lead)
                if not ok:
                    stats["dropped:" + why] += 1
                    continue
                rows.append({"url": lead, "tags": [], "source": "rssamplifier",
                             "category": q, "hintTopics": [], "hintType": None,
                             "via": "directory",
                             "directoryCat": f.get("cat", "")})
            stats["feeds named"] += len(found)
    seen, out = set(), []
    for r in rows:
        k = vocab_mod.norm_key(r["url"])
        if k in seen:
            stats["dropped:duplicate in batch"] += 1
            continue
        seen.add(k)
        out.append(r)
    with open(AMP, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(out)} feeds named by the directory -> {AMP}")
    for k, v in sorted(stats.items()):
        print(f"  {k:30} {v}")
    return 0


def amp_topic(subject):
    q = urllib.parse.urlencode({"topic": subject})
    req = urllib.request.Request(AMP_URL + "?" + q, headers=harvest.HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read(8_000_000)
            ce = r.headers.get("Content-Encoding", "")
        text = harvest.decode(raw, ce)
    except Exception:
        return []
    return [{"url": u, "cat": c} for u, c in iter_opml(text)]


def read_queries(path):
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            yield line


def amp_all(limit_per_run, max_per_host):
    """The whole directory as candidates, bounded and resumable.

    One 44 MB fetch instead of tens of thousands of queries is what the site
    itself asks for ("reading them is preferred to crawling the HTML", and robots.txt
    names this endpoint), so the download is cached under data/sources/.

    The directory is bigger than the probe budget, so the written list is bounded
    twice: per host, because 400 feeds from one publisher is not a directory a
    reader browses; and per run, because a probe pass has to finish inside a
    sitting. Ordered by host then url and skipping anything already probed, so the
    next run picks up where this one stopped instead of repeating it.
    """
    if not os.path.exists(AMP_ALL):
        req = urllib.request.Request(AMP_URL, headers=harvest.HEADERS)
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read(120_000_000)
            ce = r.headers.get("Content-Encoding", "")
        os.makedirs(os.path.dirname(AMP_ALL), exist_ok=True)
        with open(AMP_ALL, "wb") as fh:
            fh.write(raw if not ce else harvest.decode(raw, ce).encode("utf-8"))
        print(f"directory downloaded -> {AMP_ALL} ({os.path.getsize(AMP_ALL)} bytes)")
    text = open(AMP_ALL, encoding="utf-8", errors="replace").read()
    found = [{"url": u, "cat": c} for u, c in iter_opml(text)]
    probed = {r["url"] for r in read_jsonl(RESULTS)}
    by_host, out = collections.Counter(), []
    stats = collections.Counter()
    stats["directory entries"] = len(found)
    for f in sorted(found, key=lambda x: (urlparse(x["url"]).netloc.lower(), x["url"])):
        lead = clean_url(f["url"])
        ok, why = is_plausible_feed(lead)
        if not ok:
            stats["dropped:" + why] += 1
            continue
        ok, why = worth_carrying(lead)
        if not ok:
            stats["dropped:" + why] += 1
            continue
        if lead in probed:
            stats["dropped:already probed"] += 1
            continue
        host = urlparse(lead).netloc.lower()
        if by_host[host] >= max_per_host:
            stats["dropped:per-host cap"] += 1
            continue
        by_host[host] += 1
        out.append({"url": lead, "tags": [], "source": "rssamplifier",
                    "category": f.get("cat", ""), "hintTopics": [], "hintType": None,
                    "via": "directory-all"})
        if limit_per_run and len(out) >= limit_per_run:
            stats["truncated at the run limit"] += 1
            break
    return out, stats


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("sources", nargs="?")
    f.add_argument("--restart", action="store_true")
    e = sub.add_parser("extract")
    e.add_argument("--limit", type=int)
    sub.add_parser("paths")
    sub.add_parser("tag")
    s = sub.add_parser("siblings")
    s.add_argument("--max-per-host", type=int, default=1,
                   help="include hosts with up to N feeds in feeds.json")
    sub.add_parser("leads")
    pg = sub.add_parser("pages")
    pg.add_argument("sites", help="file of site URLs to ask for their feeds")
    o = sub.add_parser("oracle")
    o.add_argument("sites", nargs="?",
                   help="file of sites to ask; default is our own single-feed hosts")
    o.add_argument("--max-per-host", type=int, default=1,
                   help="with no sites file, ask hosts carrying at most N feeds")
    o.add_argument("--crawl", action="store_true",
                   help="let the index crawl the site instead of using its saved answer")
    o.add_argument("--restart", action="store_true", help="ignore the cached answers")
    o.add_argument("--max-leads-per-site", type=int, default=6,
                   help="editorial cap: shallowest feeds first, so one publisher's "
                        "257 desk feeds do not become our list's shape")
    o.add_argument("--pause", type=float, default=1.0,
                   help="seconds between queries to someone else's free service")
    a = sub.add_parser("amp")
    a.add_argument("queries", nargs="?",
                   help="file of subjects to ask the directory about (omit with --all)")
    a.add_argument("--max-per-query", type=int, default=25,
                   help="a directory this deep names hundreds of feeds for one subject")
    a.add_argument("--all", action="store_true",
                   help="the whole directory in one download, bounded and resumable")
    a.add_argument("--limit", type=int, default=1500,
                   help="with --all: candidates to emit this run, so a probe pass fits in a sitting")
    a.add_argument("--max-per-host", type=int, default=2,
                   help="with --all: feeds per host, the deepest directory on earth is still not a reason for 400 lines from one publisher")
    a.add_argument("--restart", action="store_true", help="ignore the cached answers")
    a.add_argument("--pause", type=float, default=1.0,
                   help="seconds between queries to someone else's free service")
    args = ap.parse_args()
    if args.cmd == "fetch" and args.sources:
        # A path given on the command line is the user's path, not ours (see
        # paths.py), so it is used as written.
        global SOURCES
        SOURCES = args.sources
    return {"fetch": cmd_fetch, "extract": cmd_extract,
            "paths": cmd_paths, "tag": cmd_tag,
            "siblings": cmd_siblings, "leads": cmd_leads,
            "pages": cmd_pages,
            "oracle": cmd_oracle,
            "amp": cmd_amp}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
