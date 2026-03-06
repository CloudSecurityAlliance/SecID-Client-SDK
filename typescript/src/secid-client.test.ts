/**
 * Fixture-driven tests for the TypeScript SecID client.
 *
 * Reads ../tests/fixtures.json and runs each test case against a local mock server.
 * Uses Node built-in test runner (node:test) + node:http for mocking.
 *
 * Run: npm test (in typescript/)
 */

import { describe, it, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync } from "node:fs";
import { resolve as pathResolve } from "node:path";
import { fileURLToPath } from "node:url";

import { SecIDClient } from "./secid-client.js";

// ---------------------------------------------------------------------------
// Load fixtures
// ---------------------------------------------------------------------------

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const fixturesPath = pathResolve(__dirname, "..", "..", "tests", "fixtures.json");
const fixtures = JSON.parse(readFileSync(fixturesPath, "utf-8")).tests as Fixture[];

interface Fixture {
  name: string;
  description: string;
  category: string;
  input: { secid: string; method: string };
  mock_response: {
    http_status?: number;
    body?: Record<string, unknown>;
    raw_body?: string;
    content_type?: string;
    behavior?: string;
    body_size_bytes?: number;
  };
  expected: {
    status?: string;
    best_url?: string | null;
    was_corrected?: boolean;
    resolution_result_count?: number;
    registry_result_count?: number;
    message?: string | null;
    raises_error?: boolean;
    error_contains?: string;
    request_url_contains?: string;
    request_url_not_contains?: string;
  };
}

// ---------------------------------------------------------------------------
// Mock HTTP server
// ---------------------------------------------------------------------------

let mockServer: http.Server;
let mockPort: number;
let recordedUrls: string[] = [];

// Current mock configuration
let mockConfig: Fixture["mock_response"] = {};

function configureMock(mockResponse: Fixture["mock_response"]) {
  mockConfig = mockResponse;
  recordedUrls = [];
}

function createMockServer(): Promise<number> {
  return new Promise((resolve) => {
    mockServer = http.createServer((req, res) => {
      recordedUrls.push(req.url ?? "");

      if (mockConfig.behavior === "timeout") {
        // Don't respond — let the client time out
        return;
      }

      if (mockConfig.behavior === "oversized_body") {
        res.writeHead(200, { "Content-Type": "application/json" });
        const size = mockConfig.body_size_bytes ?? 11_000_000;
        res.end(Buffer.alloc(size, 0x78)); // 'x' bytes
        return;
      }

      const status = mockConfig.http_status ?? 200;
      const contentType = mockConfig.content_type ?? "application/json";

      res.writeHead(status, { "Content-Type": contentType });

      if (mockConfig.raw_body !== undefined) {
        res.end(mockConfig.raw_body);
      } else if (mockConfig.body !== undefined) {
        res.end(JSON.stringify(mockConfig.body));
      } else {
        res.end("{}");
      }
    });

    mockServer.listen(0, "127.0.0.1", () => {
      const addr = mockServer.address();
      if (addr && typeof addr === "object") {
        mockPort = addr.port;
        resolve(addr.port);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function assertExpected(fixture: Fixture, resp: { status: string; bestUrl?: string; wasCorrected: boolean; resolutionResults: unknown[]; registryResults: unknown[]; message?: string }) {
  const expected = fixture.expected;

  if ("status" in expected && expected.status !== undefined) {
    assert.equal(resp.status, expected.status, `status mismatch`);
  }

  if ("best_url" in expected) {
    if (expected.best_url === null) {
      assert.equal(resp.bestUrl, undefined, `best_url should be undefined`);
    } else {
      assert.equal(resp.bestUrl, expected.best_url, `best_url mismatch`);
    }
  }

  if ("was_corrected" in expected) {
    assert.equal(resp.wasCorrected, expected.was_corrected, `was_corrected mismatch`);
  }

  if ("resolution_result_count" in expected) {
    assert.equal(
      resp.resolutionResults.length,
      expected.resolution_result_count,
      `resolution_result_count mismatch`,
    );
  }

  if ("registry_result_count" in expected) {
    assert.equal(
      resp.registryResults.length,
      expected.registry_result_count,
      `registry_result_count mismatch`,
    );
  }

  if ("message" in expected) {
    if (expected.message === null) {
      assert.equal(resp.message, undefined, `message should be undefined`);
    } else {
      assert.equal(resp.message, expected.message, `message mismatch`);
    }
  }

  if ("request_url_contains" in expected) {
    assert.ok(recordedUrls.length > 0, "No request recorded");
    const url = recordedUrls[recordedUrls.length - 1];
    assert.ok(
      url.includes(expected.request_url_contains!),
      `Request URL should contain '${expected.request_url_contains}', got: ${url}`,
    );
  }

  if ("request_url_not_contains" in expected) {
    assert.ok(recordedUrls.length > 0, "No request recorded");
    const url = recordedUrls[recordedUrls.length - 1];
    assert.ok(
      !url.includes(expected.request_url_not_contains!),
      `Request URL should NOT contain '${expected.request_url_not_contains}', got: ${url}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

await createMockServer();

after(() => {
  mockServer.close();
});

// Standard tests (use the mock server)
const standardFixtures = fixtures.filter(
  (f) => f.mock_response.behavior !== "connection_refused",
);

describe("SecID Client (fixtures)", () => {
  for (const fixture of standardFixtures) {
    it(fixture.name, async () => {
      configureMock(fixture.mock_response);

      const isTimeout = fixture.mock_response.behavior === "timeout";
      const timeoutMs = isTimeout ? 1000 : 5000;
      const client = new SecIDClient(`http://127.0.0.1:${mockPort}`, timeoutMs);

      if (fixture.expected.raises_error) {
        // TS client never throws — it returns SecIDResponse with status="error"
        const resp = await client.resolve(fixture.input.secid);
        assert.equal(resp.status, "error", `Expected error status for ${fixture.name}`);
        if (fixture.expected.error_contains && resp.message) {
          assert.ok(
            resp.message.toLowerCase().includes(fixture.expected.error_contains.toLowerCase()),
            `Expected '${fixture.expected.error_contains}' in message: ${resp.message}`,
          );
        }
      } else {
        const resp = await client.resolve(fixture.input.secid);
        assertExpected(fixture, resp);
      }
    });
  }
});

// Connection refused tests (no mock server — point at unused port)
const connectionRefusedFixtures = fixtures.filter(
  (f) => f.mock_response.behavior === "connection_refused",
);

describe("SecID Client (connection refused)", () => {
  for (const fixture of connectionRefusedFixtures) {
    it(fixture.name, async () => {
      const client = new SecIDClient("http://127.0.0.1:1", 2000);
      const resp = await client.resolve(fixture.input.secid);
      assert.equal(resp.status, "error", "Expected error status on connection refused");
    });
  }
});
