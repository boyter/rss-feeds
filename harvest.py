"""Fetch every feed in feeds.json and record what it actually is.

Unlike check.py this does not rewrite feeds.json. It writes harvest.jsonl, one
JSON object per feed, which is what the reclassification pass reads.

Gentle by construction:
  * 8 lanes, and every host is pinned to a single lane, so a domain is never
    hit by two requests at once (2,757 hosts, 3,375 feeds).
  * a pause between requests within a lane.
  * resumable: rerunning skips URLs already present in harvest.jsonl.

Usage:
    python3 harvest.py                 # full run, resumable
    python3 harvest.py --limit 50      # smoke test
"""

import argparse
import concurrent.futures as futures
import gzip
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
import zlib
from collections import defaultdict
from html import unescape
from urllib.parse import urlparse

OUTFILE = "harvest.jsonl"
MAX_BYTES = 60_000
TIMEOUT = 12
LANES = 8
PAUSE = 0.25

# Same approach as check.py: a plain browser User-Agent, because a bare
# urllib default gets blocked by far more sites than it protects.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) "
                  "Gecko/20100101 Firefox/97.0",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, "
              "text/xml, */*",
    # Advertise only what decode() can undo. CDNs brotli-compress responses even
    # when nothing asks for it, and there is no brotli in the standard library:
    # without this header a live feed arrives as binary and is written off as
    # not-a-feed.
    "Accept-Encoding": "gzip, deflate",
}

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
DESC_RE = re.compile(
    r"<(?:description|summary|subtitle)[^>]*>(.*?)</(?:description|summary|subtitle)>",
    re.S | re.I)
ITEM_RE = re.compile(r"<(?:item|entry)[\s>].*?</(?:item|entry)>", re.S | re.I)
CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def clean(text, limit=200):
    text = CDATA_RE.sub(r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(unescape(text).split())[:limit]


def decode(raw, content_encoding=""):
    """Undo Content-Encoding, including when the server ignored our headers.

    Several sites gzip or brotli regardless of Accept-Encoding; without this the
    body is binary and a perfectly good feed is written off as not-a-feed.
    """
    enc = (content_encoding or "").lower()
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif raw[:1] == b"\x78":
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
    text = raw.decode("utf-8", "replace")
    if "\ufffd" in text[:200] and enc:
        # Report it rather than guess. brotli has no magic number and is not in
        # the standard library, and some CDNs send it even though we asked for
        # gzip - a feed we cannot decode is unknown, not dead.
        text = f"[undecodable {enc} body]"
    return text


def probe(url):
    """Return one record for a feed URL. Never raises."""
    rec = {"url": url, "checkedAt": int(time.time())}
    body = ""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            rec["status"] = resp.getcode()
            rec["finalUrl"] = resp.geturl()
            rec["contentType"] = (resp.headers.get("content-type") or "").split(";")[0].strip()
            body = decode(resp.read(MAX_BYTES), resp.headers.get("content-encoding", ""))
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = f"HTTPError {e.code}"
        return rec
    except urllib.error.URLError as e:
        rec["status"] = 0
        rec["error"] = f"URLError {e.reason}"[:200]
        return rec
    except BaseException as e:  # noqa: BLE001 - a bad feed must not kill the run
        rec["status"] = 0
        rec["error"] = f"{type(e).__name__}: {e}"[:200]
        return rec

    head = body.lstrip("\ufeff \t\r\n").lstrip()[:300]
    if head.startswith("[undecodable"):
        rec["undecodable"] = head[13:].split(")")[0].split(" ")[0]
        rec["isFeed"] = None          # unknown, deliberately not False
        return rec
    rec["isFeed"] = head.startswith(("<?xml", "<rss", "<feed", "<rdf"))
    if not rec["isFeed"] and head.startswith("{"):
        # JSON Feed (jsonfeed.org). Common on /feed.json.
        rec["isFeed"] = "jsonfeed.org" in body[:400] or ("home_page_url" in body[:400]
                                                        and "items" in body[:2000])
        if rec["isFeed"]:
            rec["feedFormat"] = "json"
            m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', body)
            rec["title"] = json_unescape(m.group(1)) if m else ""
            rec["items"] = [json_unescape(t) for t in
                            re.findall(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', body)[1:7]]
            rec["itemCount"] = len(rec["items"])
            return rec
    if not rec["isFeed"]:
        rec["snippet"] = " ".join(body.split())[:160]
        return rec

    m = TITLE_RE.search(body)
    rec["title"] = clean(m.group(1)) if m else ""
    m = DESC_RE.search(body)
    rec["description"] = clean(m.group(1)) if m else ""
    rec["items"] = [clean(t.group(1), 160)
                    for item in ITEM_RE.findall(body)[:6]
                    if (t := TITLE_RE.search(item))]
    rec["itemCount"] = len(rec["items"])
    return rec


def json_unescape(text):
    try:
        return " ".join(json.loads('"' + text + '"').split())[:160]
    except (ValueError, TypeError):
        return text[:160]


def load_done(path):
    done = {}
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # truncated tail from an interrupted run
            done[rec.get("url")] = rec
    return done


def build_lanes(urls, lanes):
    """Pin each host to one lane so no domain is fetched concurrently."""
    by_host = defaultdict(list)
    for url in urls:
        by_host[urlparse(url).netloc.lower()].append(url)
    buckets = [[] for _ in range(lanes)]
    for host, host_urls in sorted(by_host.items(), key=lambda kv: -len(kv[1])):
        min(buckets, key=len).extend(host_urls)
    return [b for b in buckets if b]


def run_lane(lane, write_lock, out):
    results = []
    for url in lane:
        rec = probe(url)
        results.append(rec)
        with write_lock:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
        time.sleep(PAUSE)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only check the first N feeds")
    ap.add_argument("--restart", action="store_true", help="ignore harvest.jsonl progress")
    args = ap.parse_args()

    with open("feeds.json", encoding="utf-8") as fh:
        urls = [f["url"] for f in json.load(fh)]
    if args.limit:
        urls = urls[:args.limit]

    done = {} if args.restart else load_done(OUTFILE)
    todo = [u for u in urls if u not in done]
    print(f"{len(urls)} feeds, {len(done)} already harvested, {len(todo)} to fetch",
          flush=True)
    if not todo:
        return 0

    import threading
    write_lock = threading.Lock()
    lanes = build_lanes(todo, LANES)
    start = time.time()
    with open(OUTFILE, "a", encoding="utf-8") as out:
        with futures.ThreadPoolExecutor(max_workers=len(lanes)) as ex:
            for res in ex.map(lambda lane: run_lane(lane, write_lock, out), lanes):
                pass
        # progress is in the file; this is just the summary
        done = load_done(OUTFILE)

    ok = sum(1 for r in done.values() if r.get("isFeed"))
    dead = sum(1 for r in done.values() if not r.get("isFeed"))
    print(f"done in {time.time()-start:.0f}s: {len(done)} records, "
          f"{ok} look like feeds, {dead} do not", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
