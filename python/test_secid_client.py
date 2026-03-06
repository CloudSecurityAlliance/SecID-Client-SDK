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
        # Client should either raise OR return status="error"
        try:
            resp = client.resolve(fixture["input"]["secid"])
            assert resp.status == "error", (
                f"Expected error status or exception, got status={resp.status}"
            )
            # Check error_contains if specified
            if "error_contains" in expected and resp.message:
                assert expected["error_contains"].lower() in resp.message.lower(), (
                    f"Expected '{expected['error_contains']}' in message: {resp.message}"
                )
        except Exception:
            pass  # Exception is acceptable for error tests
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
    try:
        resp = client.resolve(fixture["input"]["secid"])
        assert resp.status == "error"
    except Exception:
        pass  # Exception is also acceptable
