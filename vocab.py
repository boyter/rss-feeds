"""The tag vocabulary, read from TAGS.md.

TAGS.md is the single source of truth: a tag that is not in it cannot be written
to feeds.json, because classify.py and rebuild.py both validate against this.
"""

import re

FACETS = ("topic", "region", "type", "language")
_TAG_RE = re.compile(r"`((?:%s):[a-z0-9:-]+)`" % "|".join(FACETS))


def load(path="TAGS.md"):
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


def merge_tags(keep, override, suggested, vocab):
    """Resolve the three tag sources into what gets written, and what to report.

    keep       tags already in feeds.json
    override   the human decision from overrides.jsonl, empty if there is none
    suggested  what the rules propose

    A hand decision is the whole answer for the facets it speaks to. The rules
    read item headlines, and that is not a decision: one headline mentioning AI
    put topic:ai on 273 hand-decided feeds, and a re-harvest moved the tags again
    because the week's headlines were different. The exclusion is per facet, so an
    override that settles only type: (reddit.com says "aggregator" and leaves the
    topics to pathTags) does not strip topics off a feed that matches no pathTag.

    Returns (tags, problems). Every way a tag is lost or a conflict is resolved by
    precedence is reported, never absorbed.
    """
    keep = [t for t in keep if t in vocab]
    override = [t for t in override if t in vocab]
    suggested = [t for t in suggested if t in vocab]
    problems = []
    if override:
        decided = decided_facets(override)
        keep = [t for t in keep if t.split(":", 1)[0] not in decided]
        suggested = [t for t in suggested if t.split(":", 1)[0] not in decided]
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
