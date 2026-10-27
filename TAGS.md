# Tag vocabulary

Tags are namespaced `facet:value`. Four facets, lowercase, hyphenated, singular.
A tag that is not listed here is a bug — add it to this file in the same PR, or
pick an existing one.

Every feed gets **at least one `topic:`** and **exactly one `type:`**.
`region:` and `language:` are only present when they are meaningful: an American
developer's personal blog gets no `region:`, an English feed gets no `language:`.

## topic: (subject)

Technology and software:

| tag | covers |
|---|---|
| `topic:software-engineering` | practice, craft, process, testing, teams, tooling |
| `topic:programming` | languages, compilers, algorithms, language internals |
| `topic:web-development` | HTML/CSS/JS, browsers, front-end, web platform |
| `topic:systems` | operating systems, kernels, file systems, virtualization |
| `topic:networking` | protocols, routing, DNS, networking practice |
| `topic:security` | infosec, vulnerabilities, malware, cryptography, privacy |
| `topic:ai` | machine learning, LLMs, data science as a discipline |
| `topic:data` | databases, analytics, data engineering, warehouses |
| `topic:infrastructure` | cloud, devops, containers, deployment, SRE |
| `topic:hardware` | chips, electronics, retrocomputing, robotics |
| `topic:embedded` | microcontrollers, firmware, embedded Linux |
| `topic:graphics` | rendering, ray tracing, GPUs, game engines |
| `topic:open-source` | FOSS licensing, community, project governance |
| `topic:tech-industry` | business of tech, startups, venture, product |
| `topic:gadgets` | consumer hardware, reviews, apps |
| `topic:programming:<lang>` | optional language tag, see below |

Language tags are a controlled sub-list, only where the feed is genuinely about
that language. This list is read by `vocab.py`, so it is written in full:

`topic:programming:ada`, `topic:programming:apl`, `topic:programming:assembly`,
`topic:programming:c`, `topic:programming:clojure`, `topic:programming:cpp`,
`topic:programming:csharp`,
`topic:programming:crystal`, `topic:programming:d`, `topic:programming:dart`,
`topic:programming:elixir`, `topic:programming:erlang`, `topic:programming:fortran`,
`topic:programming:fsharp`, `topic:programming:go`, `topic:programming:haskell`,
`topic:programming:java`, `topic:programming:javascript`, `topic:programming:julia`,
`topic:programming:kotlin`, `topic:programming:lisp`, `topic:programming:lua`,
`topic:programming:nim`, `topic:programming:objective-c`, `topic:programming:ocaml`,
`topic:programming:perl`, `topic:programming:php`, `topic:programming:python`,
`topic:programming:r`, `topic:programming:ruby`, `topic:programming:rust`,
`topic:programming:scala`, `topic:programming:shell`, `topic:programming:smalltalk`,
`topic:programming:sql`, `topic:programming:swift`, `topic:programming:zig`.

Non-technology:

`topic:science`, `topic:mathematics`, `topic:medicine`, `topic:environment`,
`topic:politics`, `topic:government`, `topic:military`, `topic:design`, `topic:history`, `topic:philosophy`,
`topic:economics`, `topic:finance`, `topic:business`, `topic:media`,
`topic:journalism`, `topic:sport`, `topic:gaming`, `topic:entertainment`,
`topic:transport`,
`topic:music`, `topic:art`, `topic:books`, `topic:travel`, `topic:food`,
`topic:astrology` (horoscopes, natal charts, astrological practice - a real recurring cluster; esoteric but categorizable),
`topic:health`, `topic:education`, `topic:religion`, `topic:lifestyle`, `topic:personal`

`topic:personal` is for general life-writing blogs with no dominant subject. It
is the only topic that may stand alone without a second topic.

`topic:news` is general top-stories coverage with no single subject — a
newspaper front page, a wire service. It must be paired with a `region:`, and
with a subject topic where the outlet has one (a politics paper gets
`topic:politics` as well). It replaces the old flat `news` tag, which was being
used as a type instead.

## type: (what kind of source)

| tag | covers |
|---|---|
| `type:personal-blog` | one named human writing for themselves |
| `type:vendor-blog` | company blog, including engineering blogs |
| `type:publication` | magazine / news site with staff writers |
| `type:newsletter` | email-first publication with a feed |
| `type:podcast` | audio show |
| `type:video` | YouTube / video-first |
| `type:aggregator` | linkblog, reddit, curated feeds, planet sites |
| `type:institution` | university, research lab, standards body, government |
| `type:community` | forum, mailing list, organization with members |

## region: (editorial focus, not the publisher's postcode)

`region:world`, `region:africa`, `region:asia`, `region:australia`,
`region:canada`, `region:caribbean`, `region:china`, `region:europe`,
`region:france`, `region:germany`, `region:india`, `region:ireland`,
`region:italy`, `region:japan`, `region:latin-america`, `region:middle-east`,
`region:mexico`, `region:new-zealand`, `region:nigeria`, `region:pakistan`,
`region:philippines`, `region:poland`, `region:russia`, `region:south-korea`,
`region:spain`, `region:uk`, `region:ukraine`, `region:usa`

Sub-national, only for feeds that are actually local:
`region:australia-act`, `region:australia-adelaide`, `region:australia-brisbane`,
`region:australia-melbourne`, `region:australia-nt`, `region:australia-perth`,
`region:australia-qld`, `region:australia-sydney`, `region:australia-tas`,
`region:australia-vic`, `region:australia-wa`, `region:uk-london`,
`region:us-california`, `region:us-chicago`, `region:us-dc`, `region:us-new-york`,
`region:us-texas`

## language: (only when not English, or for a translated feed)

`language:arabic`, `language:chinese`, `language:czech`, `language:english`,
`language:dutch`, `language:finnish`, `language:french`, `language:german`,
`language:hindi`, `language:italian`, `language:japanese`, `language:korean`,
`language:norwegian`, `language:polish`, `language:portuguese`, `language:russian`,
`language:spanish`, `language:ukrainian`, `language:urdu`

`language:english` is normally omitted. The one exception is a feed that is a
translation of a non-English site, where naming the language is what tells the
two feeds on the same host apart.

## Removed, and what replaced them

The old flat vocabulary had 68 tags and 80 combinations, two of which covered
70% of the file. Migrations applied:

| old | new |
|---|---|
| `technology` | dropped as a catch-all; feeds must carry a real `topic:` |
| `programming` | `topic:programming` and/or `topic:software-engineering` |
| `security` | `topic:security` |
| `news` | `type:publication` plus a real subject topic |
| `world`, `usa`, `uk`, `australia`, ... | `region:` equivalents |
| `new` + `york` (split string) | `region:us-new-york` |
| `northern` + `territory`, `nt` | `region:australia-nt` |
| `ny` | `region:us-new-york` |
| `defense`, `defence` | `topic:security` (or `topic:government` where military policy) |
| `japanese`, `english` | `language:japanese` / nothing |
| `business`, `finance`, `sport`, ... | `topic:` equivalents |
