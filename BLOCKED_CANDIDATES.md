# Candidate feeds we could not verify

Two feeds are in `feeds.json` only because they were checked by hand:
`https://dieworkwear.com/feed/` and `https://thecyberwire.com/feeds/rss.xml`.
Their CDNs serve brotli regardless of `Accept-Encoding`, so `harvest.py` cannot
read them; `curl --compressed` shows both are live RSS. They are flagged
`undecodable:br` rather than removed. If a brotli decoder ever becomes
available, re-run the harvest.

Proposed additions that returned 401/403/429 to `harvest.py`. These are real
publications that refuse a plain script with a browser User-Agent — not dead
feeds. They are **not** in `feeds.json`, because this repo does not add a feed
it has not seen answer with a feed.

To add one, confirm the URL in a browser or a feed reader first, then add it to
`candidates.jsonl` and re-run `python3 add.py probe`.

| url | outlet |
|---|---|
| https://www.politico.com/rss/politico.xml | Politico (US politics) |
| https://www.lawfareblog.com/feed | Lawfare (national security) |
| https://www.carbonbrief.org/feed/ | Carbon Brief (climate, UK) |
| https://news.mongabay.com/feed/ | Mongabay (environment) |
| https://cosmosmagazine.com/feed/ | Cosmos Magazine (science, AU) |
| https://www.sciencebasedmedicine.org/feed/ | Science-Based Medicine |
| https://www.dailymaverick.co.za/feed/ | Daily Maverick (South Africa) |
| https://www.poynter.org/feed/ | Poynter (journalism) |
| https://queue.acm.org/rss.cfm | ACM Queue (software engineering) |
| https://japantoday.com/feed | Japan Today |
| https://elpais.com/feed/ | El País (Spain, Spanish) |

Also tried and genuinely gone (404 or HTML where a feed should be), so do not
retry these without finding a new address: `sciencedaily.com/rss/all`,
`scientificamerican.com/feed/`, `ourworldindata.org/feed.xml`,
`e360.yale.edu/feed/`, `lrb.co.uk/feed`, `smithsonianmag.com/rss/`,
`newrepublic.com/feed`, `pitchfork.com/rss/reviews/albums/`,
`slate.com/feed`, `console.dev/rss`, `postgresweekly.com/feed`,
`pythonweekly.com/feed`, `scala-lang.org/blog/feed.xml`,
`julialang.org/blog/*`, `dlang.org/blog/*`, `nim-lang.org/blog/*`,
`php.net/rss/news`, `fsharpforfunandprofit.com/rss-feed/`,
`interconnects.buttondown.email/feed`, `fastspine.com/feed/`,
`brasilianafreepress.com/feed/`, `blog.crookedtimber.org/feed/`.
