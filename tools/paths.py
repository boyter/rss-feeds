"""Where the files live, in one place.

The scripts are in tools/, the working data is in data/, and the product
(feeds.json) and the prose (TAGS.md, REMOVED.md, BLOCKED_CANDIDATES.md) sit at
the root. Every path the tools use is resolved from here, so a script behaves
the same whatever directory you run it from - which matters, because the
pipeline is run by hand, by people who are not thinking about cwd.

Arguments you pass on the command line (a candidates file, --from a commit) are
left as given: those are the user's paths, not ours.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def data(name):
    """Path to a working file: harvest.jsonl, overrides.jsonl, draft.jsonl."""
    return os.path.join(DATA, name)


def root(name):
    """Path to something at the top: feeds.json, TAGS.md, REMOVED.md."""
    return os.path.join(ROOT, name)


def ensure_data():
    """Create data/ if it is missing, before anything writes into it."""
    os.makedirs(DATA, exist_ok=True)
