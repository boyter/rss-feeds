"""First-pass tag suggestions for feeds.json, from harvested titles/descriptions.

This is deliberately a *draft*. It only ever proposes tags it can point at a
keyword for, and it flags anything it is unsure about for manual review. The
vocabulary lives in TAGS.md; nothing here may invent a tag outside it.

Reads:  feeds.json, harvest.jsonl, overrides.jsonl (optional)
Writes: draft.jsonl   one record per feed, with suggested tags + confidence

Usage:
    python3 classify.py            # writes draft.jsonl, prints stats
    python3 classify.py --review   # print only the records needing review
"""

import argparse
import collections
import json
import os
import re
import sys
import vocab as vocab_mod
from urllib.parse import urlparse

# (regex over title+description+items, tags to add). Ordered; all matches apply.
# Keep these high precision: a rule that fires on the wrong feed is worse than
# no rule, because it does not get reviewed.
TOPIC_RULES = [
    (r"\b(cybersec|infosec|vulnerabilit|\bCVE\b|malware|ransomware|breach|exploit|penetration test|threat intel|phishing|cryptograph|zero[- ]day|\bsecurity\b|privacy|surveillance)", ["topic:security"]),
    (r"\b(machine learning|\bdeep learning\b|neural net|\bLLM\b|large language|transformer|GPT|\bAI\b|artificial intelligence|data science|\bMLOps\b|TensorFlow|PyTorch)", ["topic:ai"]),
    (r"\b(database|Postgres|MySQL|SQLite|Snowflake|ClickHouse|data engineering|data warehouse|analytics|business intelligence|\bETL\b|Apache Spark|Airflow)", ["topic:data"]),
    (r"\b(kubernetes|\bk8s\b|docker|container|terraform|ansible|devops|\bSRE\b|site reliability|continuous (integration|delivery|deployment)|\bCI/CD\b|observability|prometheus|cloud computing|\bAWS\b|\bAzure\b|\bGCP\b|serverless)", ["topic:infrastructure"]),
    (r"\b(browser|javascript|typescript|\bCSS\b|\bHTML\b|front[- ]?end|react|vue|svelte|\bDOM\b|web platform|progressive web|webassembly|\bWASM\b|accessibility|\bWCAG\b)", ["topic:web-development"]),
    (r"\b(kernel|operating system|\bOS dev|file system|ext4|zfs|btrfs|virtualization|hypervisor|container runtime|\bCPU\b cache|memory management|scheduler|plan 9|solaris|freebsd|openbsd|netbsd|linux)", ["topic:systems"]),
    (r"\b(network protocol|\bTCP\b|\bUDP\b|\bHTTP/|\bDNS\b|routing|bgp|\bIPv6\b|wireguard|packet|networking)", ["topic:networking"]),
    (r"\b(microcontroller|\bMCU\b|arduino|raspberry pi|fpga|\bASIC\b|transistor|circuit|soldering|3d printing|\bPCB\b|retrocomput|hardware hacking|robotics|oscilloscope)", ["topic:hardware"]),
    (r"\b(open source|open-source|\bFOSS\b|free software|\bGPL\b|\bMIT licen|copyleft|debian|fedora|ubuntu|nixos)", ["topic:open-source"]),
    (r"\b(startup|start-up|venture capital|\bVC\b|founder|fundrais|incubator|accelerator|saas business|product management|tech industry|\bsilicon valley\b)", ["topic:tech-industry"]),
    (r"\b(smartphone|iphone|android app|gadget|reviewed|unboxing|\bapp review|consumer tech)", ["topic:gadgets"]),
    (r"\b(compiler|interpreter|type system|type theory|\blanguage design\b|programming language|\bsyntax\b|\bparser\b|\bAST\b|bytecode|garbage collection|formal verification|\bPL\b research|category theory)", ["topic:programming"]),
    (r"\b(algorithm|data structure|\bbig o\b|complexity|graph algorithm|sorting)", ["topic:programming"]),
    (r"\b(testing|test suite|unit test|code review|refactor|debugging|software architecture|design pattern|clean code|software engineering|\bAgile\b|scrum|\bTDD\b)", ["topic:software-engineering"]),
    (r"\b(mathematics|\bmath\b|number theory|topology|\balgebra\b|calculus|\bstatistics\b|probability|\bphysics\b|quantum)", ["topic:mathematics"]),
    (r"\b(biology|genetics|neuroscience|chemistry|astronomy|space|climate|ecology|paleontology)", ["topic:science"]),
    (r"\b(election|parliament|senate|congress|policy|democracy|legislation|\bpolitical\b|geopolit|\bforeign policy\b)", ["topic:politics"]),
    (r"\b(economy|inflation|\bgdp\b|monetary|fiscal|market|equit|stock|bond|investing|\bfinance\b|banking|crypto currency|cryptocurrenc|\bbitcoin\b|blockchain)", ["topic:finance"]),
    (r"\b(nfl|nba|mlb|nhl|soccer|football|cricket|rugby|tennis|golf|\bf1\b|formula 1|boxing|mma|ufc|olympic|baseball|basketball|hockey)", ["topic:sport"]),
    (r"\b(video game|game design|\bgamedev\b|game development|\bxbox\b|\bplaystation\b|\bnintendo\b|steam|\broguelike|tabletop|rpg)", ["topic:gaming"]),
    (r"\b(podcast|episode|\baudio\b|interview with|listen to)", ["topic:media"]),
    (r"\b(journalism|newsroom|news media|reporting|press freedom|fact[- ]check)", ["topic:journalism"]),
    (r"\b(travel|flight|hotel|backpack)", ["topic:travel"]),
    (r"\b(recipe|cooking|food|wine|coffee)", ["topic:food"]),
    (r"\b(book review|reading list|\bbooks\b|literature|poetry|fiction)", ["topic:books"]),
    (r"\b(history|historical|archaeolog|archive of)", ["topic:history"]),
    (r"\b(medicine|clinical|patient|disease|vaccine|mental health|public health|nutrition|fitness|workout|exercise)", ["topic:health"]),
    (r"\b(teaching|classroom|curriculum|education|learning to code|pedagogy|university course)", ["topic:education"]),
    (r"\b(climate|environment|energy|\bsolar\b|emissions|recycling)", ["topic:environment"]),
    (r"\b(music|album|band|guitar|synth|vinyl)", ["topic:music"]),
    (r"\b(film|movie|cinema|television|tv review|series review)", ["topic:entertainment"]),
    (r"\b(business|company|management|consulting|marketing|sales|entrepreneur)", ["topic:business"]),
]

# Language: script-based only. Word-based guessing produced false positives on
# English text, so every other language is set by hand in overrides.jsonl.
LANG_RULES = [
    (r"[\uac00-\ud7af]", "language:korean"),
    (r"[\u3040-\u30ff]", "language:japanese"),
    (r"[\u4e00-\u9fff]", "language:chinese"),
    (r"[\u0600-\u06ff]", "language:arabic"),
    (r"[\u0400-\u04ff]", "language:russian"),
]

# ccTLD -> region. A suggestion only: a .com.au domain can be a personal blog
# with no Australian editorial focus, so these are capped at low confidence.
CC_TLD = {
    "com.au": "australia", "net.au": "australia", "org.au": "australia",
    "id.au": "australia", "edu.au": "australia", "gov.au": "australia",
    "co.uk": "uk", "org.uk": "uk", "ac.uk": "uk", "cnn": "uk",
    "co.nz": "new-zealand", "co.za": "africa", "com.ng": "nigeria",
    "co.in": "india", "com.sg": "asia", "co.jp": "japan", "ne.jp": "japan",
    "or.jp": "japan", "co.kr": "south-korea", "com.br": "latin-america",
    "com.mx": "latin-america", "com.ar": "latin-america", "fr": "france",
    "de": "germany", "es": "spain", "it": "italy", "nl": "europe",
    "ru": "russia", "cn": "china", "ca": "canada", "ie": "ireland",
    "im": None,
}

PERSONAL_HOST_HINTS = re.compile(
    r"(github\.io|gitlab\.io|blogspot\.|wordpress\.com|readthedocs\.io|"
    r"substack\.com|write\.as|medium\.com/@|neocities\.org|news\.blog|"
    r"weebly\.com|wixsite\.com|tumblr\.com|hashnode\.dev|dev\.to/@)", re.I)
VENDOR_HINTS = re.compile(r"/(blog|news|engineering|resources|insights|company)/", re.I)
PODCAST_HINTS = re.compile(r"(podcast|\brss\b.*episode)", re.I)

VOCAB = set()  # filled from TAGS.md at runtime



def host_of(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def haystack(rec):
    parts = [rec.get("title", ""), rec.get("description", "")] + rec.get("items", [])[:6]
    return " ".join(p for p in parts if p)


def region_for(host):
    for suffix in ("com.au", "co.uk", "org.uk", "ac.uk", "co.nz", "co.za", "com.ng",
                   "co.in", "com.sg", "co.jp", "ne.jp", "or.jp", "co.kr", "com.br",
                   "com.mx", "com.ar"):
        if host.endswith("." + suffix):
            return CC_TLD[suffix]
    tld = host.rsplit(".", 1)[-1]
    return CC_TLD.get(tld)


def infer_type(rec, host):
    """Guess the source type from the feed's own title.

    Only used when no host override exists, and only when the title gives a
    clear signal; a wrong type is worse than no type because it does not get
    reviewed. Returns None when the title says nothing.
    """
    title = rec.get("title", "")
    if not title:
        return None
    t = title.lower()
    if re.search(r"\bpodcast\b", t):
        return "type:podcast"
    if re.search(r"\b(news|times|post|gazette|herald|tribune|journal|monitor|telegraph|express|guardian)\b", t):
        return "type:publication"
    if re.search(r"\b(blog|journal|notes|ramblings|musings|diary|website|site)\b", t) and \
       re.search(r"[a-z]+'s|\bby [a-z]+\b", t):
        return "type:personal-blog"
    # Hugo/Jekyll default titles ("Posts on example.com", "Recent content on
    # X") are what a hand-rolled static site emits, which in this list means a
    # personal blog far more often than a company.
    if re.match(r"^(posts on|recent content on|articles on|articles —) ", t):
        return "type:personal-blog"
    if re.search(r"'[a-z]+ (blog|journal|website|site)$", t) or t.startswith("blog of "):
        return "type:personal-blog"
    return None


def suggest(rec, old_tags):
    text = haystack(rec)
    tags, why = [], []
    for pattern, added in TOPIC_RULES:
        m = re.search(pattern, text, re.I)
        if m:
            tags.extend(t for t in added if t not in tags)
            why.append(f"topic:{m.group(1)[:24]}")
    for pattern, lang in LANG_RULES:
        if re.search(pattern, text):
            if lang == "language:japanese" and re.search(r"[\uac00-\ud7af]", text):
                continue
            tags.append(lang)
            break
    host = host_of(rec["url"])
    region = region_for(host)
    if region and region not in tags:
        tags.append(f"region:{region}")
    if PERSONAL_HOST_HINTS.search(host) or PERSONAL_HOST_HINTS.search(rec["url"]):
        tags.append("type:personal-blog")
    elif PODCAST_HINTS.search(text) and "podcast" in rec["url"].lower():
        tags.append("type:podcast")
    elif VENDOR_HINTS.search(urlparse(rec["url"]).path):
        tags.append("type:vendor-blog")
    else:
        inferred = infer_type(rec, host)
        if inferred:
            tags.append(inferred)
    # carry forward old flat tags that still mean something
    legacy = {"programming": "topic:software-engineering",
              "security": "topic:security", "gaming": "topic:gaming",
              "sport": "topic:sport", "politics": "topic:politics",
              "health": "topic:health", "science": "topic:science",
              "business": "topic:business", "finance": "topic:finance",
              "entertainment": "topic:entertainment", "travel": "topic:travel",
              "podcast": "topic:media", "environment": "topic:environment"}
    for t in old_tags:
        if t in legacy and legacy[t] not in tags:
            tags.append(legacy[t])
            why.append(f"old:{t}")
    return sorted(set(t for t in tags if t in VOCAB)), why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true")
    args = ap.parse_args()

    global VOCAB
    VOCAB = vocab_mod.load()

    feeds = json.load(open("feeds.json", encoding="utf-8"))
    harvest = {}
    if os.path.exists("harvest.jsonl"):
        for line in open("harvest.jsonl", encoding="utf-8"):
            try:
                r = json.loads(line)
                harvest[r["url"]] = r
            except json.JSONDecodeError:
                pass
    overrides = {"host": {}, "url": {}}
    if os.path.exists("overrides.jsonl"):
        for line in open("overrides.jsonl", encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            # A key with a slash in it is a specific feed URL; without one it
            # is a host, and applies to every feed on that host.
            if "/" in r["key"]:
                overrides["url"][r["key"].lower()] = r["tags"]
            else:
                overrides["host"][r["key"].lower()] = r

    out, stats = [], collections.Counter()
    for feed in feeds:
        url = feed["url"]
        rec = harvest.get(url, {"url": url})
        host = host_of(url)
        old = feed.get("tags") or []
        suggested, why = suggest(rec, old)
        # A URL-level override wins outright. Otherwise the host's default tags
        # apply, plus any path rule that matches this particular feed, so a
        # site's category feeds inherit the site's topic and gain their own.
        final = overrides["url"].get(url.lower())
        if final is None:
            # A stored key may omit a query string the live URL carries
            # (feedburner aliases: /com/rCTl?format=xml). Longest match wins.
            candidates = [k for k in overrides["url"]
                          if url.lower().startswith(k + "?") or url.lower() == k]
            if candidates:
                final = overrides["url"][max(candidates, key=len)]
        if final is None and host in overrides["host"]:
            rule = overrides["host"][host]
            final = list(rule.get("tags", []))
            for needle, extra in (rule.get("pathTags") or {}).items():
                if needle in url.lower():
                    if isinstance(extra, str):
                        extra = [extra]
                    final.extend(t for t in extra if t not in final)
            why.append("host-rule")
        if final is not None:
            final = vocab_mod.normalize(final)
        topics = [t for t in (final or suggested) if t.startswith("topic:")]
        types = [t for t in (final or suggested) if t.startswith("type:")]
        needs = []
        if final is not None:
            needs = ["override"]
        else:
            if not topics:
                needs.append("no-topic")
            if not types:
                needs.append("no-type")
            if not rec.get("isFeed"):
                needs.append("not-a-feed")
        stats["needs:" + (needs[0] if needs else "clean")] += 1
        bad = [t for t in (final or suggested) if t not in VOCAB]
        if bad:
            stats["bad-tag"] += 1
            print(f"  !! tag not in TAGS.md for {url}: {bad}", file=sys.stderr)
        out.append({
            "url": url, "host": host,
            "title": rec.get("title", ""),
            "description": rec.get("description", "")[:160],
            "items": rec.get("items", [])[:3],
            "oldTags": old, "suggested": suggested, "why": why,
            "final": final, "needs": needs,
            "isFeed": rec.get("isFeed", False),
            "status": rec.get("status", 0),
            "error": rec.get("error", ""),
        })

    with open("draft.jsonl", "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"{len(out)} feeds -> draft.jsonl")
    for k, v in stats.most_common():
        print(f"  {v:5d} {k}")
    if args.review:
        for r in out:
            if r["needs"] and "override" not in r["needs"]:
                print(f"{r['host']:38s} | {r['title'][:48]:48s} | {r['description'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
