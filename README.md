# RSS-feeds

Tagged lists of RSS feeds, because sometimes you just want a machine readable list.

There are a lot of websites out there with lists of "top 100 rss feeds" however they usually belong to software that wants you to subscribe through their system. Sometimes you just want a list of the feeds so you can get the content yourself.

Thats where this repository fits in.

See `feeds.json` for a collection of all the feeds. Each entry has a `url`, a set of tags, and the `title` the feed itself reports. Tags are there because not all feeds return category information. The title is there because a list of two thousand bare URLs is hard to browse, and because it is harvested from the feed rather than typed by hand, it stays honest.

Tags are namespaced: `topic:` what it is about, `type:` what kind of source it is, `region:` editorial focus, `language:` when it isn't English. The vocabulary and the rules for adding to it are in `TAGS.md`. One feed per line, sorted by host, so a change to one feed shows up as one changed line.

If you want to add feeds submit a PR. `harvest.py` fetches every feed and records its title, description, sample items and whether it actually serves a feed; `triage.py` turns that into keep / flag / remove, feeds that stay broken get dropped, and `REMOVED.md` lists what went and why.
