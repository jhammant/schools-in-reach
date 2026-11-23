"""The "Your chances" report offer: its page placement, privacy wording and deploy check agree."""
import contextlib
import io
import re
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pipeline.seo import report_offer

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
LAMBDA = ROOT / "deploy" / "report-signups" / "lambda.mjs"


def js_date(name: str) -> date:
    """A `Date.UTC(y, m, d) / 1000` constant from lambda.mjs (JavaScript months count from 0)."""
    y, m, d = map(int, re.search(rf"export const {name} = Date\.UTC\((\d+), (\d+), (\d+)\)", LAMBDA.read_text(encoding="utf-8")).groups())
    return date(y, m + 1, d)


class PageAndPrivacy(unittest.TestCase):
    def test_results_list_has_a_hidden_offer_slot_between_the_summary_and_the_schools(self):
        # Arrange
        html = (SITE / "index.html").read_text(encoding="utf-8")

        # Act
        summary, offer, schools = (html.find(marker) for marker in ('id="list-summary"', 'id="report-offer"', 'id="school-list"'))

        # Assert
        self.assertTrue(0 < summary < offer < schools)
        self.assertIn('<div id="report-offer" class="report-offer" hidden></div>', html)

    def test_privacy_page_says_what_happens_to_a_report_email(self):
        # Arrange
        privacy = (SITE / "privacy.html").read_text(encoding="utf-8")

        # Act
        sentence = re.search(r'<p id="report-email">(.*?)</p>', privacy, re.S)

        # Assert: what is kept, where, what for, and when it goes.
        self.assertIsNotNone(sentence)
        for words in ("email address you give", "nothing else", "Amazon Web Services in London",
                      "only to send you that one message", "never share it or add it to our analytics",
                      "delete it automatically by the end of January 2027"):
            self.assertIn(words, sentence.group(1))

    def test_privacy_page_no_longer_says_it_never_asks_for_an_email_address(self):
        # Arrange
        privacy = (SITE / "privacy.html").read_text(encoding="utf-8")

        # Act
        never_asks = re.search(r"We never ask for [^.]*\.", privacy).group(0)

        # Assert
        self.assertNotIn("email", never_asks)
        self.assertNotIn("no sign-up", privacy)
        self.assertNotIn("Because we hold no personal data about you", privacy)

    def test_deletion_and_closing_dates_agree_across_endpoint_offer_and_privacy_page(self):
        # Arrange
        config = (SITE / "js" / "config.js").read_text(encoding="utf-8")
        offer = (SITE / "js" / "report-offer.js").read_text(encoding="utf-8")
        ends_on = date.fromisoformat(re.search(r'endsOn: "(\d{4}-\d{2}-\d{2})"', config).group(1))

        # Act
        delete_at, closes_at = js_date("DELETE_AT"), js_date("CLOSES_AT")

        # Assert: rows expire with a week to spare before the promised date (DynamoDB takes a few days).
        self.assertLessEqual(delete_at, date(2027, 1, 31) - timedelta(days=7))
        self.assertEqual(closes_at, ends_on + timedelta(days=1))
        self.assertEqual(ends_on, date(2027, 1, 15))
        self.assertIn("delete it by the end of January 2027", offer)


class Handler(BaseHTTPRequestHandler):
    """A stand-in endpoint; the test sets `health` and `allow_origin` on the server."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        status, body = self.server.health
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        if self.server.allow_origin:
            self.send_header("access-control-allow-origin", self.server.allow_origin)
        self.end_headers()


class DeployCheck(unittest.TestCase):
    def serve(self, health=(200, b'{"ok": true}'), allow_origin=report_offer.SITE_ORIGIN):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.health, server.allow_origin = health, allow_origin
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/sir-report/api/notify"

    def test_reads_the_endpoint_from_the_shipped_config(self):
        # Arrange
        config = (SITE / "js" / "config.js").read_text(encoding="utf-8")

        # Act
        url = report_offer.notify_url(config)

        # Assert
        self.assertEqual(url, "https://pages.hammantlabs.com/sir-report/api/notify")
        self.assertEqual(report_offer.health_url(url), "https://pages.hammantlabs.com/sir-report/api/health")

    def test_a_live_endpoint_that_accepts_the_site_passes(self):
        # Arrange
        url = self.serve()

        # Act
        problems = report_offer.check_endpoint(url, timeout=5)

        # Assert
        self.assertEqual(problems, [])

    def test_a_missing_endpoint_fails(self):
        # Arrange
        url = self.serve(health=(404, b'{"error": "this site has no server"}'))

        # Act
        problems = report_offer.check_endpoint(url, timeout=5)

        # Assert
        self.assertEqual(len(problems), 1)
        self.assertIn("answered 404", problems[0])

    def test_an_endpoint_that_refuses_the_site_fails(self):
        # Arrange
        url = self.serve(allow_origin="")

        # Act
        problems = report_offer.check_endpoint(url, timeout=5)

        # Assert
        self.assertEqual(len(problems), 1)
        self.assertIn("does not accept posts from https://www.schoolsinreach.com", problems[0])

    def test_plain_http_to_another_host_is_refused_without_a_request(self):
        # Arrange, Act
        problems = report_offer.check_endpoint("http://example.com/api/notify")

        # Assert
        self.assertIn("must be an https:// address", problems[0])

    def test_an_empty_endpoint_skips_the_check(self):
        # Arrange
        config = Path(self.enterContext(tempfile.TemporaryDirectory())) / "config.js"
        config.write_text('export const CONFIG = { parentsReport: { enabled: true, notifyUrl: "" } };', encoding="utf-8")

        # Act
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = report_offer.main(config)

        # Assert
        self.assertEqual(code, 0)
        self.assertIn("without an email box", out.getvalue())

    def test_a_config_without_the_block_fails_loudly(self):
        # Arrange, Act, Assert
        with self.assertRaises(ValueError):
            report_offer.notify_url("export const CONFIG = {};")


if __name__ == "__main__":
    unittest.main()
