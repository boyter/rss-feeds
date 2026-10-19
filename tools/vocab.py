"""The tag vocabulary, read from TAGS.md.

TAGS.md is the single source of truth: a tag that is not in it cannot be written
to feeds.json, because classify.py and rebuild.py both validate against this.
"""

import re
from urllib.parse import urlparse

import paths

FACETS = ("topic", "region", "type", "language")
_TAG_RE = re.compile(r"`((?:%s):[a-z0-9:-]+)`" % "|".join(FACETS))

# Parameters that name the reader, not the feed: how the same feed shows up twice
# in a batch of submissions. Deliberately narrow - a parameter called source= or
# ref= can be the thing that distinguishes two feeds on an API, and collapsing two
# different feeds is data loss, while keeping a tracked duplicate is one visible
# extra line.
TRACKING_PARAMS = ("utm_", "fbclid", "fb_action")


def norm_key(url):
    """The key that two spellings of the same feed share.

    Scheme, www. and a trailing slash are ignored. The query string is KEPT.
    It used to be dropped except for feedburner hosts, and that was wrong twice
    over: 41 feeds here are identified by their query - every YouTube channel
    feed is youtube.com/feeds/videos.xml with a different channel_id, NPR's
    sections differ only by ?id= - so the key collapsed distinct feeds into one,
    which refused verified additions as "already present" and would have deleted
    existing ones on the next rebuild.

    One function, not one per script: add.py and rebuild.py must agree about what
    "the same feed" means, or a feed can pass one gate and be collapsed by the
    other.
    """
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    # Parameter names are folded to lowercase, values are not. YouTube channel ids
    # are case-sensitive, so folding the value could fuse two channels into one
    # feed. Percent-encoding is left alone: the key normalizes spelling, not
    # encoding, and unquoting could fuse values a server keeps apart.
    def norm_param(kv):
        name, sep, value = kv.partition("=")
        return name.lower() + (sep + value if sep else "")
    q = "&".join(sorted(norm_param(kv) for kv in p.query.split("&")
                        if kv and not kv.split("=", 1)[0].lower().startswith(TRACKING_PARAMS)))
    return host + p.path.lower().rstrip("/") + (("?" + q) if q else "")


def load(path=paths.root("TAGS.md")):
    vocab = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            vocab.update(_TAG_RE.findall(line))
    return vocab


def validate(tags, vocab):
    """Return the tags that are not in the vocabulary."""
    return [t for t in tags if t not in vocab]


def facet(tags, name):
    prefix = name + ":"
    return [t for t in tags if t.startswith(prefix)]


# A city feed is also a country feed, but writing both says nothing the city
# tag does not already say.
_PARENT = {
    "region:australia-": "region:australia",
    "region:us-": "region:usa",
    "region:uk-london": "region:uk",
}


def normalize(tags):
    """Drop a parent region when a sub-national one is present."""
    out = list(tags)
    for child, parent in _PARENT.items():
        if any(t.startswith(child) for t in out) and parent in out:
            out.remove(parent)
    return sorted(set(out))


def decided_facets(override):
    """Which facets a hand decision speaks to - topic and/or type."""
    return {t.split(":", 1)[0] for t in override if t.split(":", 1)[0] in ("topic", "type")}


def merge_tags(keep, override, suggested, vocab, scope="url"):
    """Resolve the three tag sources into what gets written, and what to report.

    keep       tags already in feeds.json
    override   the human decision from overrides.jsonl, empty if there is none
    suggested  what the rules propose
    scope      "url" if the override names this feed, "host" if it covers a site

    A hand decision is the whole answer for the facets it speaks to. The rules
    read item headlines, and that is not a decision: one headline mentioning AI
    put topic:ai on 273 hand-decided feeds, and a re-harvest moved the tags again
    because the week's headlines were different. The exclusion is per facet, so an
    override that settles only type: (reddit.com says "aggregator" and leaves the
    topics to pathTags) does not strip topics off a feed that matches no pathTag.

    A host rule is not as specific as a URL rule, though. It generalizes over
    every feed on the site, so it may settle what kind of source the site
    publishes (type:) but it must not erase a topic a human gave to this one feed:
    the npr.org host rule stripped topic:health from the Global Health section
    feed, and topic:ai from a science channel about AI research. Only URL rules
    replace what is already there, and when they do it is reported, never absorbed.

    Returns (tags, problems).
    """
    raw_keep, raw_override, raw_suggested = keep, override, suggested
    keep = [t for t in keep if t in vocab]
    override = [t for t in override if t in vocab]
    suggested = [t for t in suggested if t in vocab]
    problems = []
    # A tag that leaves TAGS.md disappears from the output, and whether it should
    # have is a human decision: feeds.json and overrides.jsonl both hold
    # decisions. Name the file the dead tag came from, or the writer loses a hand
    # decision in silence - and the writer is the one that ships the file.
    for name, src in (("tags in feeds.json", raw_keep),
                      ("overrides.jsonl", raw_override),
                      ("rules", raw_suggested)):
        bad = [t for t in src if t not in vocab]
        if bad:
            problems.append(f"dropped tags not in TAGS.md ({name}): {bad}")
    if override:
        decided = decided_facets(override)
        suggested = [t for t in suggested if t.split(":", 1)[0] not in decided]
        strip = decided if scope == "url" else (decided & {"type"})
        # Only a tag that actually vanishes is worth reporting: an override that
        # repeats what feeds.json already said displaces nothing, and reporting
        # that made 2,127 normal feeds look like a defect in every rebuild.
        replaced = [t for t in keep
                    if t.split(":", 1)[0] in strip and t not in override]
        if replaced:
            problems.append(f"override replaced {len(replaced)} tag(s) already in "
                            f"feeds.json: {replaced}")
        keep = [t for t in keep if t.split(":", 1)[0] not in strip]
    tags = normalize(sorted(set(keep) | set(override) | set(suggested)))
    types = facet(tags, "type")
    if len(types) > 1:
        # Name every malformed source, not just the winner: a losing source
        # holding two types is still a broken rule, and reporting only the winner
        # makes the other one invisible.
        sources = (("override", override), ("tags in feeds.json", keep), ("rule", suggested))
        for name, src in sources:
            st = sorted(facet(src, "type"))
            if len(st) > 1:
                problems.append(f"BAD SOURCE: the {name} carries {len(st)} types {st}")
        src_name, src = next(((n, s) for n, s in sources if facet(s, "type")), ("nothing", []))
        src_types = sorted(facet(src, "type"))
        chosen = src_types[0] if src_types else sorted(types)[0]
        tags = [t for t in tags if not t.startswith("type:") or t == chosen]
        problems.append(f"conflicting type: {types} -> kept {chosen} from {src_name}")
    return tags, problems
