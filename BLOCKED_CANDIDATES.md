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
a candidates file and re-run `python3 tools/add.py probe`.

## Blocked, but real

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
| https://www.ilpost.it/feed/ | Il Post (Italy, Italian) |
| https://www.texasmonthly.com/feed/ | Texas Monthly (region:us-texas) |
| https://blockclubchicago.org/feed/ | Block Club Chicago (region:us-chicago) |
| https://washingtoncitypaper.com/feed/ | Washington City Paper (region:us-dc) |

## Answers, but serves nothing

Checked 2026-10-19: HTTP 200 and something that parses, but no title and no
items. Not added — an empty line in the list is not a feed.

| url | outlet |
|---|---|
| https://fsharp.org/feed.xml | F# foundation (would fill `topic:programming:fsharp`) |

## Also tried and genuinely gone

404, or HTML where a feed should be, or the domain does not resolve. Do not
retry these without finding a new address.

News and general: `sciencedaily.com/rss/all`, `scientificamerican.com/feed/`,
`ourworldindata.org/feed.xml`, `e360.yale.edu/feed/`, `lrb.co.uk/feed`,
`smithsonianmag.com/rss/`, `newrepublic.com/feed`, `pitchfork.com/rss/reviews/albums/`,
`slate.com/feed`, `console.dev/rss`, `postgresweekly.com/feed`,
`pythonweekly.com/feed`, `golem.de/news/rss`, `repubblica.it/rss/homepage/rss.xml`,
`20minutos.es/rss/ultimas/`, `standard.co.uk/feed`, `dcist.com/feed`,
`chicago.suntimes.com/rss`, `abc.net.au/news/rss`, `abc.net.au/news/feed/5295740`,
`watoday.com.au/xml/rss/`, `westaustralian.org.au` (domain gone),
`aljazeera.net/xml/rss/all.xml`, `yle.fi/uutiset/rss` (serves HTML),
`brisbanetimes.com.au/xml/rss/`.

Language and project sites, all still wanted for the thin tags in TAGS.md:
`scala-lang.org/blog/feed.xml`, `julialang.org/blog/*` (but `julialang.org/feed.xml`
works), `dlang.org/blog/*`, `nim-lang.org/blog/*`, `php.net/rss/news`,
`fsharpforfunandprofit.com/rss-feed/`, `fortran-lang.org/feed.xml`,
`fortran-lang.org/blog/feed.xml`, `ziglang.org/feeds/rss.xml`,
`ziglang.org/blog/feed/`, `lisp-lang.org/feed.xml`, `perl.com/feed/`,
`lua.org/feeds/news.rss`, `ada-lang.io/feed.xml`, `compgroups.net/*` (domain gone),
`lispjournal.com` (domain gone), `cysh.dev` (domain gone),
`modernsql.dev` (domain gone), `use-the-index-luke.com` (certificate does not
match the hostname), `feeds.fireside.fm/rubyrogues/rss`,
`feeds.megaphone.fm/GLT1832039091`, `feeds.simplecast.com/l2kMjAU6`,
`interconnects.buttondown.email/feed`, `fastspine.com/feed/`,
`brasilianafreepress.com/feed/`, `blog.crookedtimber.org/feed/`.

## Gaps still open

Worth another attempt with a real address found in a browser:
`region:caribbean`, `region:australia-brisbane`, `-vic`, `-wa`,
`language:finnish`, `language:italian`, `language:spanish` (only La Vanguardia
so far), `topic:programming:ada`, `-apl` (only the Dyalog vendor blog),
`-fortran`, `-lua`, `-nim`, `-d`, `-scala`, `-shell`, and `type:video`
(YouTube channel ids are guesswork; two of three probes were wrong channels).
