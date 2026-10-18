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
