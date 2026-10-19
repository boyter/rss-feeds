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
    python3 harvest.py --retry-failed  # re-fetch only records that are not feeds

What a record holds, and what it does not claim:
  * isFeed - the body began with XML/RSS/Atom. A page that is HTML but names a
    feed gets that link recorded in altFeed, and is still not a feed: swapping a
    URL in feeds.json is a human decision, but the lead should not be lost.
  * itemCount - items found in the fetched head (the head is capped at 60 KB, so
    a huge feed's count is of the head, not the whole feed). itemsSampled is how
    many titles were kept in `items`, which is capped at six; conflating the two
    once recorded a 200-item feed as having 6.
  * charset - set when the body was not valid UTF-8 and had to be decoded by
    declared charset or, failing that, cp1252. utf-8-with-replacement would have
    stored a mangled title as if the feed wrote it that way.
  * truncated - set when the stream ended early, or when Content-Encoding lied
    about the body and the raw bytes were used instead.
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
import paths
from html import unescape
from urllib.parse import urljoin, urlparse

OUTFILE = paths.data("harvest.jsonl")
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
ALT_FEED_RE = re.compile(
    r"""<link[^>]+rel=["']alternate["'][^>]*type=["']application/(?:rss|atom)\+xml"""
    r"""[^>]*href=["']([^"']+)""", re.I)


def declared_charset(content_type, raw_head):
    m = re.search(r"charset=([A-Za-z0-9_.:-]+)", content_type or "", re.I)
    if m:
        return m.group(1)
    m = re.search(rb"""encoding=["']?([A-Za-z0-9_.:-]+)""", raw_head[:200])
    return m.group(1).decode("ascii") if m else ""


# Longest first: the UTF-16-LE mark is a prefix of the UTF-32-LE one.
BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def encoding_shape(raw):
    """Name a UTF-16/UTF-32 encoding if the body looks like one and carries no mark.

    An ASCII feed written in UTF-16-LE is *also* valid UTF-8, because NUL is a
    legal UTF-8 byte. It therefore decodes "cleanly" into "<?\x00m\x00l\x00...",
    nothing reports an error, and the harvester records a live feed as
    not-a-feed. No validity check can catch that; only the shape of the bytes can.

    UTF-32 is tested first because its bytes also satisfy the UTF-16 test - three
    NULs in four contains a NUL in every two - and decoding UTF-32 as UTF-16
    produces NUL-stuffed text that no longer parses, under a note that says the
    wrong thing.
    """
    head = raw[:200]
    if len(head) < 16:
        return ""
    quads = len(head) // 4
    n32_le = sum(1 for i in range(0, len(head) - 3, 4)
                 if head[i + 1] < 0x20 and head[i + 2] < 0x20 and head[i + 3] < 0x20)
    n32_be = sum(1 for i in range(0, len(head) - 3, 4)
                 if head[i] < 0x20 and head[i + 1] < 0x20 and head[i + 2] < 0x20)
    # A UTF-32 body satisfies the UTF-16 test perfectly (three small bytes in four
    # contains a small byte in every two), so it is tested first: losing here
    # means being decoded as UTF-16, which yields NUL-stuffed text under a note
    # that says the wrong thing.
    if quads >= 4 and n32_le >= quads * 0.5:
        return "utf-32-le"
    if quads >= 4 and n32_be >= quads * 0.5:
        return "utf-32-be"
    pairs = len(head) // 2
    # "below 0x20", not "== 0". An ASCII feed has NUL on the alternate byte; a
    # Cyrillic, Greek, Hebrew or Arabic one has a constant small byte instead
    # (0x04, 0x03, 0x05), and the old test only ever saw the ASCII case - a
    # Cyrillic feed in UTF-16 with no mark decoded as UTF-8 mojibake and was
    # recorded not-a-feed with nothing reported as wrong. Printable text never
    # reaches this ratio by accident, because real characters are 0x20 and up.
    n_le = sum(1 for i in range(0, len(head) - 1, 2) if head[i + 1] < 0x20)
    n_be = sum(1 for i in range(0, len(head) - 1, 2) if head[i] < 0x20)
    if n_le >= pairs * 0.7:
        return "utf-16-le"
    if n_be >= pairs * 0.7:
        return "utf-16-be"
    # Out of scope, deliberately: CJK and Hangul in UTF-16 with no mark (high
    # byte 0x4E-0xD7) is invisible to this test. Such a body is also invalid XML -
    # UTF-16 entities require a mark - so no feed client reads it either.
    return ""


def decode_text(raw, content_type):
    """Decode a body without silently rewriting bytes we cannot read.

    utf-8 with errors="replace" turns a Latin-1 feed title into U+FFFD and the
    harvest then stores a mangled title as if it were the feed's own. Try utf-8
    strictly, then whatever the feed declared, and only then guess cp1252 - and
    say which we did, so the record admits it guessed.

    cp1252 goes last, and never before a declared charset, because it accepts
    every byte: one half-cut character becomes a whole feed of replacement
    characters. The byte cap cuts the head wherever it lands and can split a
    multi-byte character; that is our truncation, not the feed's fault, so the
    partial tail is dropped and the text kept instead of the feed written off as
    undecodable. That is how a live Cyrillic podcast got flagged dead.
    """
    cs = declared_charset(content_type, raw)
    # A byte order mark is the body stating its own encoding, which beats any
    # guess and any absent header: the prolog of a UTF-16 feed is unreadable to a
    # byte regex, and decoding it as anything else fills the text with NULs and a
    # live feed stops parsing.
    lead = raw.lstrip(b" \t\r\n")
    for bom, enc in BOMS:
        if lead.startswith(bom):
            try:
                return lead.decode(enc), f"decoded as {enc} (byte order mark)"
            except UnicodeDecodeError:
                break
    guess = encoding_shape(raw)
    if guess:
        try:
            return raw.decode(guess), f"decoded as {guess} (no byte order mark)"
        except UnicodeDecodeError as e:
            # A fixed-width body cut between the two bytes of one character. If
            # this is not handled the body falls through to utf-8, which accepts
            # every byte of UTF-16 and returns NULs interleaved with the text - a
            # live feed recorded as not-a-feed with nothing reported as wrong.
            if e.reason in ("truncated data", "unexpected end of data") and e.start >= len(raw) - 4:
                why = ("tail cut by the byte cap" if len(raw) >= MAX_BYTES - 8
                       else "dropped an odd trailing byte")
                return raw[:e.start].decode(guess, "ignore"), \
                       f"decoded as {guess} (no byte order mark), {why}"
            pass
    # utf-8 is tried before the declared charset because it is self-validating: a feed that misdeclares
    # a permissive charset still decodes cleanly, and a genuinely Latin-1 feed
    # falls through to what it declared.
    order = ["utf-8"] + ([cs] if cs and cs.lower().replace("-", "") != "utf8" else [])
    for enc in order:
        try:
            return raw.decode(enc), ("" if enc == "utf-8" else f"decoded as declared {enc}")
        except LookupError:
            continue
        except UnicodeDecodeError as e:
            # The byte cap cuts the head wherever it lands and can split a
            # multi-byte character. That is our truncation, not the feed's fault,
            # so the partial tail is dropped and the text kept. That is how a live
            # Cyrillic podcast came to be flagged undecodable.
            # A cut by the byte cap. "unexpected end of data" is a split UTF-8
            # sequence; "truncated data" is what a fixed-width encoding reports
            # when the cap lands between the two bytes of one character. Only
            # credible when the body actually reached the cap - otherwise a short
            # body that merely ends on a high byte gets blamed on us.
            if (e.reason in ("unexpected end of data", "truncated data")
                    and e.start >= len(raw) - 4 and len(raw) >= MAX_BYTES - 8):
                return raw[:e.start].decode(enc, "ignore"), f"decoded as {enc}, tail cut by the byte cap"
    # The bad bytes are in the middle of the body. Choose the smaller lie. A
    # handful of corrupt bytes in an otherwise UTF-8 feed is not a licence to
    # decode the whole thing as cp1252: that garbles every legitimate accented and
    # Cyrillic character to paper over one byte. Replace the few, and count them.
    text = raw.decode("utf-8", "replace")
    bad = text.count("\ufffd")
    high = sum(1 for b in raw if b >= 0x80)
    # A few corrupt bytes among many that decode fine is damage inside a UTF-8
    # body. But when most of the high bytes are themselves invalid the body is not
    # UTF-8 at all: b"Title: caf\xe9" is one high byte and one invalid byte, and
    # calling that UTF-8 rewrites é to U+FFFD and stores it as the feed's title.
    if bad and bad * 2 <= high:
        return text, f"utf-8 with {bad} invalid byte(s) replaced"
    note = "decoded as cp1252" + (f", though it declared {cs}" if cs else ", charset undeclared")
    return raw.decode("cp1252", "replace"), note


def clean(text, limit=200):
    text = CDATA_RE.sub(r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(unescape(text).split())[:limit]


def decompressor_for(enc, head):
    """Pick an incremental decompressor from the header, or from the magic bytes.

    Incremental matters: the whole body is never buffered before inflating, so
    the MAX_BYTES cap can cut a gzip stream in half without making the result
    undecodable. Returns None for encodings we cannot undo (brotli) and for
    plain bodies.
    """
    enc = (enc or "").lower()
    if enc == "br" or head[:1] == b"\x8b" and head[:2] != b"\x1f\x8b":
        return "br", None
    if enc in ("gzip", "x-gzip") or head[:2] == b"\x1f\x8b":
        return "gzip", zlib.decompressobj(16 + zlib.MAX_WBITS)
    if enc in ("deflate", "x-deflate") or head[:1] == b"\x78":
        return "deflate", zlib.decompressobj()
    return enc or "identity", None


def looks_compressed(b):
    """True if the bytes carry a gzip or *valid* zlib header.

    The zlib check is the header checksum, not a list of magic pairs: a list
    once omitted 0x78 0x5e (default-level deflate) and treated a real deflate
    body as binary.
    """
    if b[:2] == b"\x1f\x8b":
        return True
    return len(b) >= 2 and b[0] == 0x78 and ((b[0] << 8) | b[1]) % 31 == 0


def read_body(resp, cap=MAX_BYTES):
    """Read the response body, inflating as it arrives, capped on decoded bytes.

    The cap used to be applied to the *compressed* bytes: `resp.read(60000)`
    cut a gzip stream mid-flight, gzip.decompress then raised EOFError (which is
    not an OSError, so it escaped the handler) and live feeds — ProPublica, The
    Intercept, PC Gamer, Salon, Lex Fridman — were recorded as not feeds.
    """
    enc = (resp.headers.get("content-encoding") or "").lower()
    out = bytearray()
    raw = bytearray()
    name, dec = None, None
    note = ""
    capped = False
    while True:
        try:
            part = resp.read1(8192)
        except AttributeError:            # a response without read1()
            part = resp.read(max(0, cap - len(out)))
        except Exception as e:            # truncated chunked body, connection reset
            if not out:
                raise
            note = f"{type(e).__name__}: {e}"
            break
        if not part:
            break
        raw += part
        if name is None and len(raw) < 4:
            # Too few bytes to tell gzip from identity: the magic is two bytes
            # and a zlib header is a checksum over two more. A server that
            # flushes one byte first would otherwise have its compressed body
            # recorded verbatim as identity - a live feed, read as garbage, with
            # nothing reported as wrong.
            continue
        if name is None:
            # Sniffing late means the buffered prefix belongs to the decoder, not
            # to `part`: handing it only the newest chunk loses the first bytes.
            name, dec = decompressor_for(enc, raw)
            chunk = bytes(raw)
        else:
            chunk = part
        if dec is None:
            out += chunk
        else:
            try:
                out += dec.decompress(chunk)
            except zlib.error as e:
                note = f"zlib: {e}"
                if not out and not looks_compressed(raw):
                    # The header claimed gzip/deflate, the bytes disagree, and
                    # nothing has been produced yet. Some servers and CDNs send
                    # an identity body under a gzip Content-Encoding. Switch to
                    # identity and keep reading: breaking here would leave a
                    # body truncated to the first chunk, which still loses the
                    # tail of a live feed.
                    out = bytearray(raw)
                    dec, name = None, "identity"
                    note += " header lied about encoding"
                else:
                    break
        if len(out) >= cap:
            # Checked before the eof test, because one read can inflate past the
            # cap and end the stream in the same call: a repetitive feed
            # compressed 400:1 in a test, so a 4 KB response arrived as one chunk
            # and became 1.7 MB with no note. The cap is the bound on what we
            # hold, so it has to be applied to the bytes produced, not only
            # inspected between chunks.
            if len(out) > cap:
                out = out[:cap]
            capped = True
            break
        if dec is not None and dec.eof:
            break
    if name is None and raw:
        # The whole body arrived in fewer than four bytes; sniff it after all.
        name, dec = decompressor_for(enc, bytes(raw))
        if dec is not None:
            try:
                out = bytearray(dec.decompress(bytes(raw)))
            except zlib.error:
                out = bytearray()
    if dec is not None and not out and raw and not looks_compressed(raw):
        # The stream ended on the chunk that failed to inflate.
        return bytes(raw), "identity", (note + " header lied about encoding").strip()
    if capped:
        # Nothing raises when a large feed is simply cut at the cap, compressed
        # or not, so the record has to say that the title and itemCount below
        # describe a head rather than the whole feed.
        note = (note + " " + "body capped at %d bytes" % cap).strip()
    elif dec is not None and not dec.eof:
        # A deflate stream that inflates without error and still never reaches
        # its end marker: the server sent less than it claimed.
        note = (note + " inflate stream ended before its end marker").strip()
    return bytes(out), name or (enc or "identity"), note


def decode(raw, content_encoding=""):
    """Undo Content-Encoding for a body already in memory (fallback path).

    Several sites gzip or brotli regardless of Accept-Encoding; without this the
    body is binary and a perfectly good feed is written off as not-a-feed.
    """
    enc = (content_encoding or "").lower()
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError):
            # Truncated stream: inflate what arrived rather than losing the feed.
            try:
                raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
            except zlib.error:
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
            raw, enc, note = read_body(resp)
            if note:
                rec["truncated"] = note[:120]
            if enc == "br":
                body = f"[undecodable {enc} body]"
            else:
                body, cs_note = decode_text(raw, rec.get("contentType", ""))
                if cs_note:
                    rec["charset"] = cs_note
                    if "tail cut" in cs_note:
                        # The head was cut mid-character by the byte cap: the
                        # title and item count below are of a shortened body, and
                        # the record has to say so where truncation is read.
                        rec["truncated"] = (rec.get("truncated", "") + " " + cs_note).strip()
                if "\ufffd" in body[:200] and enc not in ("identity", ""):
                    body = f"[undecodable {enc} body]"
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
            rec["itemsSampled"] = len(rec["items"])
            # itemCount is how many items were in the fetched head, not how many
            # were kept: items is capped at six, and calling the sample a count
            # recorded a 200-item feed as having 6.
            rec["itemCount"] = max(0, body.count('"title"') - 1)
            return rec
    if not rec["isFeed"]:
        rec["snippet"] = " ".join(body.split())[:160]
        # A page that is not itself a feed but names one. Recorded, never
        # followed: swapping a URL in feeds.json is a human decision, but the
        # lead should not be thrown away.
        alt = ALT_FEED_RE.findall(body)
        if alt:
            rec["altFeed"] = [urljoin(rec.get("finalUrl", url), a)
                              for a in dict.fromkeys(alt)][:3]
        return rec

    m = TITLE_RE.search(body)
    rec["title"] = clean(m.group(1)) if m else ""
    m = DESC_RE.search(body)
    rec["description"] = clean(m.group(1)) if m else ""
    rec["items"] = [clean(t.group(1), 160)
                    for item in ITEM_RE.findall(body)[:6]
                    if (t := TITLE_RE.search(item))]
    rec["itemsSampled"] = len(rec["items"])
    rec["itemCount"] = len(ITEM_RE.findall(body))
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


def was_feed(rec):
    """Did this record say the URL serves a feed?

    A record already marked `regressed` counts as yes: it was a feed, and the
    flag has to survive the next retry, or the second run forgets the feed ever
    worked and the guard that keeps it off the removal list disappears.
    """
    return bool(rec.get("isFeed") or rec.get("regressed"))


def run_lane(lane, write_lock, out, prior=None):
    results = []
    for url in lane:
        rec = probe(url)
        # A URL that answered as a feed in an earlier pass and does not now is a
        # regression, not a dead feed: mark it so triage flags it for a human
        # instead of removing it. Only --retry-failed (or a re-harvest over an
        # existing file) can know this, because it is the only run that sees both
        # generations.
        if prior and prior.get(url) and not rec.get("isFeed"):
            rec["regressed"] = True
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
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-fetch only the URLs whose record is not a feed "
                         "(dead, blocked, or mis-decoded). Resumable: a later "
                         "record for the same URL wins over an earlier one.")
    ap.add_argument("--prior", metavar="FILE",
                    help="a previous harvest.jsonl to compare against: a URL that "
                         "was a feed there and is not now is marked regressed, so "
                         "triage flags it for a human instead of removing it. Use "
                         "this whenever a run replaces an existing file.")
    args = ap.parse_args()

    with open(paths.root("feeds.json"), encoding="utf-8") as fh:
        urls = [f["url"] for f in json.load(fh)]
    if args.limit:
        urls = urls[:args.limit]

    done = {} if args.restart else load_done(OUTFILE)
    if args.retry_failed:
        todo = [u for u in urls if not done.get(u, {}).get("isFeed")]
    else:
        todo = [u for u in urls if u not in done]
    print(f"{len(urls)} feeds, {len(done)} already harvested, {len(todo)} to fetch",
          flush=True)
    if not todo:
        return 0

    import threading
    write_lock = threading.Lock()
    # Which URLs were feeds before this run. Captured before fetching, so a
    # record written mid-run cannot overwrite the evidence of what came before.
    # A record already marked regressed counts as "was a feed": the flag has to
    # survive the next retry, or the second run forgets the feed ever worked and
    # the guard that keeps it off the removal list disappears.
    prior = {u: was_feed(r) for u, r in done.items()}
    if args.prior:
        for u, r in load_done(args.prior).items():
            prior[u] = was_feed(r) or prior.get(u, False)
    lanes = build_lanes(todo, LANES)
    start = time.time()
    with open(OUTFILE, "a", encoding="utf-8") as out:
        with futures.ThreadPoolExecutor(max_workers=len(lanes)) as ex:
            for res in ex.map(lambda lane: run_lane(lane, write_lock, out, prior), lanes):
                pass
        # progress is in the file; this is just the summary
        done = load_done(OUTFILE)

    ok = sum(1 for r in done.values() if r.get("isFeed"))
    dead = sum(1 for r in done.values() if not r.get("isFeed"))
    print(f"done in {time.time()-start:.0f}s: {len(done)} records, "
          f"{ok} look like feeds, {dead} do not", flush=True)
    regressed = [u for u, r in done.items() if r.get("regressed")]
    if regressed:
        print(f"{len(regressed)} were feeds in the prior file and are not now - "
              "flagged for a human, never removed automatically:")
        for u in regressed[:20]:
            r = done[u]
            print(f"   {u[:72]} {r.get('error') or r.get('status') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
