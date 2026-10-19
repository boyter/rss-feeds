"""The byte layer: what the harvester fetches, and how it reads what came back.

Every case in this file is a bug that actually happened. The comment says which,
because the point is not coverage — it is that a fix stays fixed. Six review
passes over this code found new ways for a live feed to be recorded as dead, and
not one of them was visible from outside the function it lived in.

Run:  python3 -m unittest
"""

import gzip
import threading
import unittest
import zlib

import harvest


class Resp:
    """A stand-in for a urllib response: fixed chunks, one header."""

    def __init__(self, chunks, encoding=None):
        self.chunks = list(chunks)
        self.headers = {"content-encoding": encoding} if encoding else {}

    def read1(self, n):
        return self.chunks.pop(0) if self.chunks else b""


def chunks_of(body, size=8192):
    return [body[i:i + size] for i in range(0, len(body), size)]


FEED = ("<?xml version='1.0'?><rss><channel>"
        "<title>Александр Токарев — Café</title></channel></rss>")


def is_prolog(text):
    """What harvest.probe would accept as the start of a feed."""
    return text.lstrip("\ufeff \t\r\n").lstrip().startswith(("<?xml", "<rss", "<feed", "<rdf"))


class ReadBody(unittest.TestCase):
    """Content-Encoding is a claim. The body is the evidence."""

    def test_honest_gzip(self):
        raw, enc, note = harvest.read_body(Resp(chunks_of(gzip.compress(FEED.encode()))))
        self.assertEqual(raw, FEED.encode())
        self.assertEqual(enc, "gzip")
        self.assertEqual(note, "")

    def test_header_lying_about_the_encoding_keeps_the_whole_body(self):
        # Servers and CDNs do send an identity body under a gzip header. The
        # first fix for this returned "the bytes read so far", and decompression
        # fails on the first chunk, so a 24 KB feed came back as 8 KB: still a
        # feed, still missing its tail, still recorded as one.
        body = FEED.encode() + b"<item><title>pad pad pad</title></item>" * 900
        self.assertGreater(len(body), 8192)
        raw, enc, note = harvest.read_body(Resp(chunks_of(body), "gzip"))
        self.assertEqual(len(raw), len(body), "body was truncated by the fallback")
        self.assertEqual(enc, "identity")
        self.assertIn("lied", note)

    def test_a_body_that_is_garbage_stays_garbage(self):
        # The fallback must not turn junk into a feed we then have to explain.
        raw, enc, _ = harvest.read_body(Resp([b"\x00\x01\x02not gzip at all" * 10], "gzip"))
        self.assertFalse(is_prolog(raw.decode("utf-8", "replace")))

    def test_truncated_gzip_keeps_what_inflated(self):
        # Capping *compressed* bytes at 60 KB rather than decoded ones produced
        # EOFError on live feeds: ProPublica, The Intercept, PC Gamer, Salon.
        whole = gzip.compress(b"<rss><channel>" + b"<item><title>x</title></item>" * 4000)
        raw, enc, note = harvest.read_body(Resp([whole[: len(whole) // 2]], "gzip"))
        self.assertTrue(raw.startswith(b"<rss"))
        self.assertIn("inflate stream ended", note)

    def test_gzip_magic_with_a_broken_stream_is_not_called_a_lie(self):
        # If the magic bytes agree the header, an empty result is our
        # truncation, not the server's dishonesty. The note has to say which.
        raw, enc, note = harvest.read_body(Resp([b"\x1f\x8b\x08\x00\x00\x00\x00\x00"], "gzip"))
        self.assertNotEqual(enc, "identity")
        self.assertNotIn("lied", note)

    def test_zlib_headers_are_checked_by_checksum_not_by_a_magic_list(self):
        # A list of two-byte magics once omitted 0x78 0x5e - default-level
        # deflate - and a real deflate body was written off as binary.
        for flg in (0x01, 0x5e, 0x9c, 0xda):
            self.assertTrue(harvest.looks_compressed(bytes([0x78, flg]) + b"\x00" * 8),
                            "0x78 0x%02x is a valid zlib header" % flg)
        self.assertFalse(harvest.looks_compressed(b"\x00\x00\x00\x00"))
        self.assertTrue(harvest.looks_compressed(gzip.compress(b"x")))


class DecodeText(unittest.TestCase):
    """Encoding is established in order of trust: mark, shape, utf-8, declared, cp1252."""

    def dec(self, raw, ct=""):
        return harvest.decode_text(raw, ct)

    def test_utf8_decodes_with_no_note(self):
        text, note = self.dec(FEED.encode())
        self.assertEqual(text, FEED)
        self.assertEqual(note, "")

    def test_byte_order_marks_are_read(self):
        for enc in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            bom = {
                "utf-16-le": b"\xff\xfe", "utf-16-be": b"\xfe\xff",
                "utf-32-le": b"\xff\xfe\x00\x00", "utf-32-be": b"\x00\x00\xfe\xff",
            }[enc]
            text, note = self.dec(bom + FEED.encode(enc), "")
            self.assertTrue(is_prolog(text), enc)
            self.assertNotIn("\x00", text, enc)
            self.assertIn("byte order mark", note)

    def test_utf16_without_a_mark_is_not_mistaken_for_utf8(self):
        # The trap no validity check can see: an ASCII feed in UTF-16-LE is also
        # *valid* UTF-8, because NUL is a legal UTF-8 byte. It decodes with no
        # error into "<?\x00m\x00l\x00...", nothing is reported wrong, and the
        # harvester records a live feed as not-a-feed.
        for enc in ("utf-16-le", "utf-16-be"):
            text, note = self.dec(FEED.encode(enc), "")
            self.assertTrue(is_prolog(text), enc)
            self.assertNotIn("\x00", text, enc)
            self.assertIn(enc, note)

    def test_utf32_without_a_mark_is_not_mistaken_for_utf16(self):
        # Three NULs in four contains a NUL in every two, so UTF-32 satisfies the
        # UTF-16 test perfectly. Decoding it as UTF-16 gives NUL-stuffed text
        # under a note that says the wrong thing.
        for enc in ("utf-32-le", "utf-32-be"):
            text, note = self.dec(FEED.encode(enc), "")
            self.assertTrue(is_prolog(text), enc)
            self.assertNotIn("\x00", text, enc)
            self.assertIn(enc, note)

    def test_shape_check_does_not_fire_on_ordinary_text(self):
        for raw, ct in ((FEED.encode(), ""),
                        (FEED.replace("Александр Токарев", "Plain Name").encode(), ""),
                        ("<rss><title>Café élèves</title>".encode("latin-1"), "")):
            text, _ = self.dec(raw, ct)
            self.assertNotIn("\x00", text)

    def test_byte_cap_cutting_a_character_keeps_the_text(self):
        # The cap cuts the head wherever it lands. That is our truncation, not
        # the feed's fault: this once flagged a live Cyrillic podcast dead.
        body = (b"<rss><channel>" + "café".encode() * 20000)[:harvest.MAX_BYTES - 1] + b"\xc3"
        self.assertEqual(len(body), harvest.MAX_BYTES)
        text, note = self.dec(body)
        self.assertTrue(is_prolog(text))
        self.assertIn("tail cut by the byte cap", note)

    def test_a_body_over_the_cap_says_it_is_only_a_head(self):
        # Nothing raises when a large feed is simply cut at the cap, so the
        # record has to state that itemCount describes the head, not the feed.
        body = b"<rss><channel>" + b"<item><title>x</title></item>" * 4000
        self.assertGreater(len(body), harvest.MAX_BYTES)
        raw, enc, note = harvest.read_body(Resp(chunks_of(body)))
        self.assertLessEqual(len(raw), harvest.MAX_BYTES + 8192)
        self.assertIn("capped", note)

    def test_a_short_body_ending_on_a_high_byte_is_not_blamed_on_the_cap(self):
        # "tail cut" is only credible when the body reached the cap. Otherwise a
        # genuine cp1252 body loses its accents and the record lies about why.
        text, note = self.dec(b"Title: caf\xe9")
        self.assertEqual(text, "Title: café")
        self.assertNotIn("tail cut", note)
        self.assertIn("cp1252", note)

    def test_cp1252_is_reachable(self):
        # utf-8 with errors="ignore" never fails, so a fallback placed after it
        # is dead code: accented bytes were silently deleted instead of mapped.
        body = "<rss><title>Café élèves naïve résumé</title>".encode("latin-1") + b"x" * 40
        text, note = self.dec(body, "")
        self.assertIn("Café élèves naïve résumé", text)
        self.assertIn("cp1252", note)

    def test_one_corrupt_byte_does_not_garble_a_utf8_body(self):
        # One bad byte in the middle of a Cyrillic feed is damage inside UTF-8.
        # Decoding the whole body as cp1252 to paper over it garbles every
        # legitimate multi-byte character in the title.
        raw = FEED.encode()
        text, note = self.dec(raw[:20] + b"\xc2" + raw[21:], "")
        self.assertIn("Александр Токарев", text)
        self.assertIn("invalid byte", note)

    def test_a_lying_declared_charset_does_not_beat_utf8(self):
        # utf-8 is self-validating: a feed that declares iso-8859-1 and is
        # actually UTF-8 must still decode cleanly.
        text, note = self.dec(FEED.encode(), "application/xml; charset=iso-8859-1")
        self.assertEqual(text, FEED)
        self.assertEqual(note, "")

    def test_a_honest_declared_charset_is_used(self):
        text, note = self.dec("Café sécurité".encode("cp1252"), "text/xml; charset=windows-1252")
        self.assertEqual(text, "Café sécurité")
        self.assertIn("declared windows-1252", note)

    def test_empty_body_is_empty_and_says_nothing(self):
        text, note = self.dec(b"")
        self.assertEqual(text, "")
        self.assertEqual(note, "")


class RegressedRecords(unittest.TestCase):
    """A feed that worked last pass and does not now is a question, not a deletion."""

    def setUp(self):
        self.saved, harvest.PAUSE = harvest.probe, 0

    def tearDown(self):
        harvest.probe = self.saved

    def run_one(self, rec, prior):
        import io
        buf = io.StringIO()
        harvest.run_lane([rec["url"]], threading.Lock(), buf, prior=prior)
        return __import__("json").loads(buf.getvalue())

    def test_a_feed_that_stops_answering_is_marked(self):
        rec = self.run_one({"url": "https://x.test/feed", "isFeed": None, "error": "HTTPError 404"},
                           {"https://x.test/feed": True})
        self.assertTrue(rec.get("regressed"))

    def test_a_url_that_never_worked_is_not(self):
        rec = self.run_one({"url": "https://y.test/feed", "isFeed": None, "error": "HTTPError 404"},
                           {"https://y.test/feed": False})
        self.assertIsNone(rec.get("regressed"))

    def test_the_flag_is_sticky_across_retries(self):
        # If a regressed record did not count as "was a feed", the second retry
        # of a flaky URL would forget it ever worked, and the guard that keeps it
        # off the removal list would disappear exactly when it is needed most.
        self.assertTrue(harvest.was_feed({"isFeed": None, "regressed": True}))
        self.assertTrue(harvest.was_feed({"isFeed": True}))
        self.assertFalse(harvest.was_feed({"isFeed": None, "error": "gone"}))


if __name__ == "__main__":
    unittest.main()
