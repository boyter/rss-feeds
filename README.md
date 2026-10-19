# RSS-feeds

Tagged lists of RSS feeds, because sometimes you just want a machine readable list.

There are a lot of websites out there with lists of "top 100 rss feeds" however they usually belong to software that wants you to subscribe through their system. Sometimes you just want a list of the feeds so you can get the content yourself.

Thats where this repository fits in.

See `feeds.json` for a collection of all the feeds. Each entry has a `url`, a set of tags, and the `title` the feed itself reports. Tags are there because not all feeds return category information. The title is there because a list of two thousand bare URLs is hard to browse, and because it is harvested from the feed rather than typed by hand, it stays honest.

Tags are namespaced: `topic:` what it is about, `type:` what kind of source it is, `region:` editorial focus, `language:` when it isn't English. The vocabulary and the rules for adding to it are in `TAGS.md`. One feed per line, sorted by host, so a change to one feed shows up as one changed line.

If you want to add feeds submit a PR. `harvest.py` fetches every feed and records its title, description, sample items and whether it actually serves a feed; `triage.py` turns that into keep / flag / remove, and `REMOVED.md` lists what went and why. A feed that only refuses a script is flagged and kept, and a feed that worked in a previous pass is never removed on one bad response — a false removal is data loss, a false keep is one dead line.

To add one feed, append a line to `feeds.json` with a `url` and tags from `TAGS.md` — the harvest fills in the title. For a batch, put them in `candidates.jsonl` and run `python3 add.py probe` then `add.py merge`: nothing joins the list until it has been seen answering with a real feed. Sites that refuse the harvester are parked in `BLOCKED_CANDIDATES.md` rather than guessed in.

Changing the tooling? `python3 -m unittest` runs the suite: no dependencies, no build, no network. It exists because this code spends most of its life handling other people's broken bytes — a `Content-Encoding` header that lies, a body cut mid-character, UTF-16 with no mark that is also valid UTF-8 — and every one of those was a live feed recorded dead until something pinned it. A change to the decoder, the verdict order or the tag merge comes with a test that fails before the fix.
