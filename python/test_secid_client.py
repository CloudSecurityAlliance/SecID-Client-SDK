"""Fixture-driven tests for the Python SecID client.

Reads ../tests/fixtures.json and runs each test case against a local mock server.
No external dependencies — uses stdlib http.server + pytest (or unittest).

Run: pytest python/test_secid_client.py -v
"""

import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pytest

from secid_client import SecIDClient

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures.json"


def load_fixtures():
    with open(FIXTURES_PATH) as f:
        return json.load(f)["tests"]


FIXTURES = load_fixtures()


def fixture_ids():
    return [t["name"] for t in FIXTURES]


# ---------------------------------------------------------------------------
# Mock HTTP server
# ---------------------------------------------------------------------------

class MockHandler(BaseHTTPRequestHandler):
    """Serves canned responses from fixture data. Records request URLs."""

    response_body = b"{}"
    response_status = 200
    response_content_type = "application/json"
    recorded_urls = []
    hang = False
    oversized_bytes = 0

    def do_GET(self):
        MockHandler.recorded_urls.append(self.path)

        if MockHandler.hang:
            # Sleep long enough that the client should time out
            time.sleep(10)
            return

        if MockHandler.oversized_bytes > 0:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"x" * MockHandler.oversized_bytes)
            return

        self.send_response(MockHandler.response_status)
        self.send_header("Content-Type", MockHandler.response_content_type)
        self.end_headers()
        self.wfile.write(MockHandler.response_body)

    def log_message(self, format, *args):
        pass  # Suppress request logging


def start_mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def configure_mock(mock_response):
    """Configure MockHandler class vars from fixture mock_response."""
    MockHandler.recorded_urls = []
    MockHandler.hang = False
    MockHandler.oversized_bytes = 0
    MockHandler.response_status = 200
    MockHandler.response_content_type = "application/json"
    MockHandler.response_body = b"{}"

    behavior = mock_response.get("behavior")
    if behavior == "timeout":
        MockHandler.hang = True
        return
    if behavior == "oversized_body":
        MockHandler.oversized_bytes = mock_response["body_size_bytes"]
        return
    if behavior == "connection_refused":
        return  # Handled specially in the test

    if "raw_body" in mock_response:
        MockHandler.response_body = mock_response["raw_body"].encode()
        MockHandler.response_content_type = mock_response.get("content_type", "text/html")
    elif "body" in mock_response:
        MockHandler.response_body = json.dumps(mock_response["body"]).encode()

    MockHandler.response_status = mock_response.get("http_status", 200)


# ---------------------------------------------------------------------------
# Server fixture (shared across the module)
# ---------------------------------------------------------------------------

_server = None
_port = None


@pytest.fixture(scope="module")
def mock_server():
    global _server, _port
    if _server is None:
        _server, _port = start_mock_server()
    yield _port
    _server.shutdown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def standard_tests():
    """Return fixture entries that use a normal mock server (not connection_refused)."""
    return [t for t in FIXTURES if t["mock_response"].get("behavior") != "connection_refused"]


def connection_refused_tests():
    """Return fixture entries that need no server (connection refused)."""
    return [t for t in FIXTURES if t["mock_response"].get("behavior") == "connection_refused"]


@pytest.mark.parametrize(
    "fixture",
    standard_tests(),
    ids=[t["name"] for t in standard_tests()],
)
def test_fixture(fixture, mock_server):
    port = mock_server
    configure_mock(fixture["mock_response"])
    expected = fixture["expected"]

    # Use short timeout for timeout tests
    is_timeout = fixture["mock_response"].get("behavior") == "timeout"
    timeout = 2 if is_timeout else 10

    client = SecIDClient(base_url=f"http://127.0.0.1:{port}", timeout=timeout)

    if expected.get("raises_error"):
        # The Python client never raises: every failure is status="error".
        resp = client.resolve(fixture["input"]["secid"])
        assert resp.status == "error", f"Expected error status, got status={resp.status}"
        if "error_contains" in expected:
            assert resp.message and expected["error_contains"].lower() in resp.message.lower(), (
                f"Expected '{expected['error_contains']}' in message: {resp.message}"
            )
        return

    # Normal test: call resolve and check expected fields
    resp = client.resolve(fixture["input"]["secid"])

    if "status" in expected:
        assert resp.status == expected["status"], (
            f"status: expected {expected['status']}, got {resp.status}"
        )

    if "best_url" in expected:
        if expected["best_url"] is None:
            assert resp.best_url is None, f"best_url: expected None, got {resp.best_url}"
        else:
            assert resp.best_url == expected["best_url"], (
                f"best_url: expected {expected['best_url']}, got {resp.best_url}"
            )

    if "was_corrected" in expected:
        assert resp.was_corrected == expected["was_corrected"], (
            f"was_corrected: expected {expected['was_corrected']}, got {resp.was_corrected}"
        )

    if "resolution_result_count" in expected:
        actual = len(resp.resolution_results)
        assert actual == expected["resolution_result_count"], (
            f"resolution_result_count: expected {expected['resolution_result_count']}, got {actual}"
        )

    if "registry_result_count" in expected:
        actual = len(resp.registry_results)
        assert actual == expected["registry_result_count"], (
            f"registry_result_count: expected {expected['registry_result_count']}, got {actual}"
        )

    if "message" in expected:
        if expected["message"] is None:
            assert resp.message is None, f"message: expected None, got {resp.message}"
        else:
            assert resp.message == expected["message"], (
                f"message: expected {expected['message']}, got {resp.message}"
            )

    # Encoding assertions: check the URL the client actually sent
    if "request_url_contains" in expected:
        assert len(MockHandler.recorded_urls) > 0, "No request recorded"
        url = MockHandler.recorded_urls[-1]
        assert expected["request_url_contains"] in url, (
            f"Request URL should contain '{expected['request_url_contains']}', got: {url}"
        )

    if "request_url_not_contains" in expected:
        assert len(MockHandler.recorded_urls) > 0, "No request recorded"
        url = MockHandler.recorded_urls[-1]
        assert expected["request_url_not_contains"] not in url, (
            f"Request URL should NOT contain '{expected['request_url_not_contains']}', got: {url}"
        )


@pytest.mark.parametrize(
    "fixture",
    connection_refused_tests(),
    ids=[t["name"] for t in connection_refused_tests()],
)
def test_connection_refused(fixture):
    # Point client at a port where nothing is listening
    client = SecIDClient(base_url="http://127.0.0.1:1", timeout=2)
    resp = client.resolve(fixture["input"]["secid"])
    assert resp.status == "error"


# ── Untrusted-response hardening (audit findings F-08, F-10-02) ──

from secid_client import SecIDResponse, _validate_url, _sanitize_terminal  # noqa: E402


def test_validate_url_scheme_allowlist():
    assert _validate_url("https://www.cve.org/CVERecord?id=CVE-2021-44228")
    assert _validate_url("http://example.com/x")
    for bad in ("javascript:alert(1)", "data:text/html,x", "file:///etc/passwd",
                "vbscript:msgbox(1)", "//evil.example/x", "/relative", "", None):
        assert _validate_url(bad) is None, f"{bad!r} must be rejected"


def test_best_url_rejects_hostile_scheme():
    # A hostile resolver returns a javascript: URL as the highest-weight result.
    r = SecIDResponse(secid_query="x", status="found",
                      results=[{"weight": 100, "url": "javascript:fetch('//evil')"}])
    assert r.best_url is None
    # A valid https result is returned unchanged.
    r2 = SecIDResponse(secid_query="x", status="found",
                       results=[{"weight": 100, "url": "https://example.com/ok"}])
    assert r2.best_url == "https://example.com/ok"


def test_sanitize_terminal_strips_control_chars():
    assert _sanitize_terminal("https://x/\x1b[2Jfake") == "https://x/[2Jfake"
    assert _sanitize_terminal("plain text") == "plain text"


def test_sanitize_terminal_accepts_non_strings():
    assert _sanitize_terminal(123) == "123"
    assert _sanitize_terminal(None) == ""
    assert isinstance(_sanitize_terminal({"a": 1}), str)


# ── Hostile resolver responses (audit finding H2) ──
#
# The resolver is untrusted. None of these may raise; each must come back as
# a SecIDResponse whose helpers work.

import socketserver  # noqa: E402


class _RawHandler(BaseHTTPRequestHandler):
    status = 200
    body = b""
    delay = 0.0
    truncate = False

    def do_GET(self):
        if _RawHandler.delay:
            # Send headers promptly, then stall mid-body: a read timeout,
            # not a connect timeout.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b'{"status":')
            self.wfile.flush()
            time.sleep(_RawHandler.delay)
            return
        self.send_response(_RawHandler.status)
        self.send_header("Content-Type", "application/json")
        if _RawHandler.truncate:
            self.send_header("Content-Length", str(len(_RawHandler.body) + 50))
        self.end_headers()
        self.wfile.write(_RawHandler.body)

    def log_message(self, format, *args):
        pass


class _ThreadedServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


@pytest.fixture(scope="module")
def raw_server():
    server = _ThreadedServer(("127.0.0.1", 0), _RawHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _serve(body, status=200, delay=0.0, truncate=False):
    _RawHandler.body = body if isinstance(body, bytes) else json.dumps(body).encode()
    _RawHandler.status = status
    _RawHandler.delay = delay
    _RawHandler.truncate = truncate


def _exercise(resp):
    """Touch every helper; none may raise on a hostile response."""
    resp.best_url, resp.was_corrected, resp.resolution_results, resp.registry_results
    return resp


@pytest.mark.parametrize("body", [
    b"null", b"[]", b"42", b'"found"', b"true", b"", b"   ",
], ids=["null", "array", "number", "string", "bool", "empty", "whitespace"])
def test_non_object_body_is_error(raw_server, body):
    _serve(body)
    resp = _exercise(SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z"))
    assert resp.status == "error"
    assert resp.results == []


def test_wrongly_typed_envelope_fields(raw_server):
    _serve({"secid_query": 7, "status": ["found"], "results": {"a": 1}, "message": 5})
    resp = _exercise(SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z"))
    assert resp.secid_query == "secid:x/y/z"
    assert resp.status == "error"
    assert resp.results == []
    assert resp.message is None


def test_non_dict_results_and_mixed_weights(raw_server):
    _serve({"status": "found", "results": [
        17, "junk", None, [1, 2],
        {"secid": "a", "weight": None, "url": "https://a.example/"},
        {"secid": "b", "weight": "90", "url": "https://b.example/"},
        {"secid": "c", "weight": True, "url": "https://c.example/"},
        {"secid": "d", "weight": 87.5, "url": "https://d.example/"},
        {"secid": "e", "weight": 90, "url": "https://e.example/"},
        {"secid": "f", "weight": 99, "url": 12345},
        {"secid": "g", "data": {"k": "v"}},
    ]})
    resp = _exercise(SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z"))
    assert resp.status == "found"
    assert len(resp.results) == 7  # the four non-objects are dropped
    assert [r["secid"] for r in resp.resolution_results] == ["e", "d"]
    assert resp.best_url == "https://e.example/"
    assert len(resp.registry_results) == 1


def test_non_utf8_body(raw_server):
    _serve(b"\xff\xfe\xfa not utf-8")
    assert SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z").status == "error"


def test_non_utf8_error_body(raw_server):
    _serve(b"\xff\xfe\xfa not utf-8", status=502)
    resp = SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z")
    assert resp.status == "error"
    assert resp.message.startswith("HTTP 502")


def test_error_status_with_null_json_body(raw_server):
    _serve(b"null", status=500)
    resp = SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z")
    assert resp.status == "error"
    assert resp.message.startswith("HTTP 500")


def test_truncated_body(raw_server):
    _serve(b'{"status": "fo', truncate=True)
    assert SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z").status == "error"


def test_read_timeout_mid_body(raw_server):
    _serve(b"", delay=3)
    resp = SecIDClient(raw_server, timeout=1).resolve("secid:x/y/z")
    assert resp.status == "error"
    assert "timeout" in resp.message.lower()


def test_deeply_nested_json(raw_server):
    _serve(b"[" * 100000 + b"]" * 100000)
    assert SecIDClient(raw_server, timeout=5).resolve("secid:x/y/z").status == "error"


@pytest.mark.parametrize("base_url", ["not a url", "ftp://example.com", ""])
def test_unusable_base_url(base_url):
    resp = SecIDClient(base_url, timeout=2).resolve("secid:x/y/z")
    assert resp.status == "error"


def test_cli_survives_hostile_values(monkeypatch, capsys):
    import secid_client

    hostile = SecIDResponse(secid_query="q", status="corrected", results=[
        {"secid": 42, "weight": 100, "url": "https://ok.example/"},
    ])
    monkeypatch.setattr(secid_client.SecIDClient, "resolve", lambda self, s: hostile)
    monkeypatch.setattr(secid_client.sys, "argv", ["secid", "secid:x/y/z"])
    secid_client.main()
    out = capsys.readouterr()
    assert out.out.strip() == "https://ok.example/"
    assert "corrected to: 42" in out.err


def test_unpaired_surrogate_secid():
    resp = SecIDClient("http://127.0.0.1:1", timeout=2).resolve("secid:x/y/\ud800")
    assert resp.status == "error"
    assert "Unicode" in resp.message


def test_user_agent_carries_version(mock_server):
    import secid_client

    configure_mock({"http_status": 200, "body": {"status": "found", "results": []}})
    captured = {}
    orig = MockHandler.do_GET

    def spy(self):
        captured["ua"] = self.headers.get("User-Agent")
        orig(self)

    MockHandler.do_GET = spy
    try:
        SecIDClient(base_url=f"http://127.0.0.1:{mock_server}", timeout=5).resolve("secid:x/y/z")
    finally:
        MockHandler.do_GET = orig
    assert captured["ua"] == f"secid-python-client/{secid_client.__version__}"
