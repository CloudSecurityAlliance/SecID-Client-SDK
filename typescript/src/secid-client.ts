/**
 * SecID client — resolve security identifiers to URLs.
 *
 * Zero runtime dependencies (fetch only).
 *
 * SecID is a universal grammar for security knowledge:
 *     secid:type/namespace/name[@version]#subpath
 *
 * API: GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded}
 *
 * IMPORTANT: The # character in SecID strings must be encoded as %23 in the
 * URL query parameter. This is the #1 failure mode for new clients.
 *
 * Usage:
 *     import { SecIDClient } from "@cloudsecurityalliance/secid";
 *     const client = new SecIDClient();
 *     const response = await client.resolve("secid:advisory/mitre.org/cve#CVE-2021-44228");
 *     console.log(response.bestUrl);
 */

export const VERSION = "0.1.0";

const DEFAULT_BASE_URL = "https://secid.cloudsecurityalliance.org";
const DEFAULT_TIMEOUT_MS = 30_000; // 30 seconds
const MAX_RESPONSE_BYTES = 10 * 1024 * 1024; // 10 MB

async function readBodyWithByteLimit(resp: Response, maxBytes: number): Promise<string> {
  const stream = resp.body;
  if (!stream) return "";

  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value) continue;

    totalBytes += value.byteLength;
    if (totalBytes > maxBytes) {
      try {
        await reader.cancel();
      } catch {
        // Best-effort cancel; limit error still propagates below.
      }
      throw new Error(`Response exceeds ${maxBytes} byte limit`);
    }
    chunks.push(value);
  }

  const merged = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(merged);
}

/** A single result that resolved to a URL. */
export interface ResolutionResult {
  secid: string;
  weight: number;
  url: string;
  content_type?: string;        // MIME type (e.g., "text/html", "application/json")
  parsability?: string;          // "structured" or "scraped"
  schema?: string;               // SecID reference to data schema
  parsing_instructions?: string; // SecID reference to parsing instruction doc
  auth?: string;                 // Free-text auth description
}

/** A single result containing registry/browsing data. */
export interface RegistryResult {
  secid: string;
  data: Record<string, unknown>;
}

/** Raw result from the API — either resolution or registry type. */
export type SecIDResult = ResolutionResult | RegistryResult;

/** Response from the SecID resolve API. */
export class SecIDResponse {
  /** The query string echoed back (decoded form). */
  readonly secidQuery: string;
  /** One of: found, corrected, related, not_found, error. */
  readonly status: string;
  /** Result objects — either resolution or registry type. */
  readonly results: SecIDResult[];
  /** Guidance text on not_found/error, undefined otherwise. */
  readonly message?: string;

  constructor(data: {
    secid_query: string;
    status: string;
    results: SecIDResult[];
    message?: string | null;
  }) {
    this.secidQuery = data.secid_query;
    this.status = data.status;
    // Keep only object entries: the getters below read properties off each
    // result, and a hostile resolver can put anything in the array.
    this.results = Array.isArray(data.results) ? data.results.filter(isObject) : [];
    this.message = data.message ?? undefined;
  }

  /**
   * Highest-weight valid URL from resolution results, or undefined.
   * Only absolute http(s) URLs count (see validateUrl). If the top result
   * carries a hostile or malformed URL, the next valid one is returned.
   */
  get bestUrl(): string | undefined {
    const resolved = this.resolutionResults;
    return resolved.length > 0 ? resolved[0].url : undefined;
  }

  /** True if the server corrected the input. */
  get wasCorrected(): boolean {
    return this.status === "corrected";
  }

  /**
   * Only results with a numeric weight and a valid http(s) url, sorted by
   * weight descending. A missing, null, string, or non-finite weight is not a
   * resolution result (sorting it as 0 or NaN would corrupt the order), and a
   * url that fails validateUrl (javascript:, data:, relative, ...) is dropped.
   */
  get resolutionResults(): ResolutionResult[] {
    return this.results
      .filter((r): r is ResolutionResult => {
        const w = (r as { weight?: unknown }).weight;
        return typeof w === "number" && Number.isFinite(w)
          && validateUrl((r as { url?: unknown }).url) !== undefined;
      })
      .sort((a, b) => b.weight - a.weight);
  }

  /** Only results with data (registry/browsing info). */
  get registryResults(): RegistryResult[] {
    return this.results
      .filter((r): r is RegistryResult => "data" in r);
  }
}

/** True for a non-null, non-array object. */
function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Build a SecIDResponse from an untrusted parsed JSON object, type-checking
 * each field. Wrong-typed fields fall back to defaults.
 */
function envelope(data: Record<string, unknown>, secid: string): SecIDResponse {
  const { secid_query, status, results, message } = data;
  return new SecIDResponse({
    secid_query: typeof secid_query === "string" ? secid_query : secid,
    status: typeof status === "string" && status !== "" ? status : "error",
    results: Array.isArray(results) ? (results.filter(isObject) as unknown as SecIDResult[]) : [],
    message: typeof message === "string" ? message : undefined,
  });
}

// The resolver response is untrusted (a hostile, federated, or MITM'd resolver
// is in scope). Only absolute http(s) URLs may be surfaced. The check is done
// by hand rather than with `new URL()` so that all three reference clients
// apply exactly the same rule: the WHATWG parser accepts "http:evil",
// "http:///evil" and "http:\\evil" as URLs with host "evil"; Python and Go do not.
const ALLOWED_URL_SCHEMES = new Set(["https", "http"]);

/**
 * Return url only if it is an absolute http(s) URL with a host, else undefined.
 *
 * Rules (identical in the Python, TypeScript and Go clients):
 *   1. a non-empty string with no ASCII control characters or spaces;
 *   2. begins with "http://" or "https://" (scheme case-insensitive);
 *   3. the authority (up to the first "/", "?", "#" or backslash), minus any
 *      "userinfo@", is non-empty and does not start with ":".
 */
function validateUrl(url: unknown): string | undefined {
  if (typeof url !== "string" || url.length === 0) return undefined;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000- \u007F]/.test(url)) return undefined;
  const sep = url.indexOf("://");
  if (sep === -1 || !ALLOWED_URL_SCHEMES.has(url.slice(0, sep).toLowerCase())) return undefined;
  const rest = url.slice(sep + 3);
  const end = rest.search(/[/?#\\]/);
  const authority = end === -1 ? rest : rest.slice(0, end);
  const host = authority.slice(authority.lastIndexOf("@") + 1);
  if (host === "" || host.startsWith(":")) return undefined;
  return url;
}

/**
 * Percent-encode a SecID for the `secid` query parameter.
 *
 * encodeURIComponent leaves `!'()*` unencoded; encoding them too makes the
 * output byte-identical to Python's quote(s, safe="") and the Go client, so
 * all three reference clients send the same request for the same SecID.
 */
function encodeSecID(secid: string): string {
  return encodeURIComponent(secid).replace(
    /[!'()*]/g,
    (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
  );
}

/** HTTP client for the SecID resolve API. */
export class SecIDClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  /**
   * @param baseUrl - API base URL. Defaults to the public SecID service.
   * @param timeoutMs - Request timeout in milliseconds. Defaults to 30 seconds.
   */
  constructor(baseUrl: string = DEFAULT_BASE_URL, timeoutMs: number = DEFAULT_TIMEOUT_MS) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
  }

  /**
   * Resolve a SecID string to URL(s).
   *
   * The # character is automatically encoded as %23 in the query parameter.
   *
   * @param secid - Full SecID string, e.g. "secid:advisory/mitre.org/cve#CVE-2021-44228"
   * @returns Never rejects for network, HTTP, or response-format problems:
   *   those come back as status "error" with an explanatory message.
   */
  async resolve(secid: string): Promise<SecIDResponse> {
    const error = (message: string) =>
      new SecIDResponse({ secid_query: secid, status: "error", results: [], message });

    let encoded: string;
    try {
      encoded = encodeSecID(secid);
    } catch {
      // encodeURIComponent throws URIError on a lone UTF-16 surrogate.
      return error("SecID is not valid Unicode (unpaired surrogate)");
    }
    const url = `${this.baseUrl}/api/v1/resolve?secid=${encoded}`;

    // Transport: fetch + bounded body read. Nothing in resolve() throws —
    // every failure becomes status="error".
    let body: string;
    let httpStatus: number;
    let ok: boolean;
    try {
      const resp = await fetch(url, {
        headers: {
          Accept: "application/json",
          "User-Agent": "secid-typescript-client/1.0",
        },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      httpStatus = resp.status;
      ok = resp.ok;
      const contentLength = resp.headers.get("content-length");
      if (contentLength && parseInt(contentLength, 10) > MAX_RESPONSE_BYTES) {
        try {
          await resp.body?.cancel();
        } catch {
          // Best-effort; the size error is what matters.
        }
        return error(`Response exceeds ${MAX_RESPONSE_BYTES} byte limit`);
      }
      body = await readBodyWithByteLimit(resp, MAX_RESPONSE_BYTES);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.startsWith("Response exceeds ")) return error(msg);
      // AbortSignal.timeout rejects with a TimeoutError DOMException, both
      // while waiting for headers and while streaming the body.
      const name = (err as { name?: unknown } | null)?.name;
      if (name === "TimeoutError" || name === "AbortError") {
        return error(`Request timeout after ${this.timeoutMs}ms: ${msg}`);
      }
      return error(`Connection error: ${msg}`);
    }

    // Parsing: a separate step, so a bad body is not reported as a
    // connection problem.
    let data: unknown;
    try {
      data = JSON.parse(body);
    } catch (err) {
      if (!ok) return error(`HTTP ${httpStatus}: ${body.slice(0, 200)}`);
      const msg = err instanceof Error ? err.message : String(err);
      return error(`Invalid response (not JSON): ${msg}`);
    }
    if (!isObject(data)) {
      if (!ok) return error(`HTTP ${httpStatus}: ${body.slice(0, 200)}`);
      const kind = data === null ? "null" : Array.isArray(data) ? "array" : typeof data;
      return error(`Invalid response: expected a JSON object, got ${kind}`);
    }
    return envelope(data, secid);
  }

  /**
   * Resolve a SecID and return the highest-weight URL, or undefined.
   */
  async bestUrl(secid: string): Promise<string | undefined> {
    return (await this.resolve(secid)).bestUrl;
  }

  /**
   * Cross-source search: find an identifier across all sources of a type.
   *
   * Equivalent to resolve(`secid:${type}/${identifier}`).
   *
   * @param type - SecID type (advisory, weakness, ttp, control, capability, methodology, disclosure, regulation, entity, reference).
   * @param identifier - The identifier to search for, e.g. "CVE-2021-44228".
   */
  async lookup(type: string, identifier: string): Promise<SecIDResponse> {
    return this.resolve(`secid:${type}/${identifier}`);
  }
}
