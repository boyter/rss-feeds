# RSS-feeds

Tagged lists of RSS feeds, because sometimes you just want a machine readable list.

There are a lot of websites out there with lists of "top 100 rss feeds" however they usually belong to software that wants you to subscribe through their system. Sometimes you just want a list of the feeds so you can get the content yourself.

Thats where this repository fits in.

See `feeds.json` for a collection of all the feeds. Feeds include a collection of tags to get categorize the content because not all feeds return this information. Everything else such as title is not included, because feeds should include this information for you.

If you want to add feeds submit a PR. The `check.py` script will be run every now and then in order to confirm feeds actually return something and otherwise track the errors, with the intention to remove the feed at some point if it remains broken.
