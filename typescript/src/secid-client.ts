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
 *     import { SecIDClient } from "secid";
 *     const client = new SecIDClient();
 *     const response = await client.resolve("secid:advisory/mitre.org/cve#CVE-2021-44228");
 *     console.log(response.bestUrl);
 */

export const VERSION = "0.1.0";

const DEFAULT_BASE_URL = "https://secid.cloudsecurityalliance.org";
const DEFAULT_TIMEOUT_MS = 30_000; // 30 seconds
const MAX_RESPONSE_BYTES = 10 * 1024 * 1024; // 10 MB

/** A single result that resolved to a URL. */
export interface ResolutionResult {
  secid: string;
  weight: number;
  url: string;
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
    this.results = data.results ?? [];
    this.message = data.message ?? undefined;
  }

  /** Highest-weight URL from resolution results, or undefined. */
  get bestUrl(): string | undefined {
    const resolved = this.resolutionResults;
    return resolved.length > 0 ? resolved[0].url : undefined;
  }

  /** True if the server corrected the input. */
  get wasCorrected(): boolean {
    return this.status === "corrected";
  }

  /** Only results with weight + url, sorted by weight descending. */
  get resolutionResults(): ResolutionResult[] {
    return this.results
      .filter((r): r is ResolutionResult => "weight" in r && "url" in r)
      .sort((a, b) => b.weight - a.weight);
  }

  /** Only results with data (registry/browsing info). */
  get registryResults(): RegistryResult[] {
    return this.results
      .filter((r): r is RegistryResult => "data" in r);
  }
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
   */
  async resolve(secid: string): Promise<SecIDResponse> {
    const encoded = secid.replace(/#/g, "%23");
    const url = `${this.baseUrl}/api/v1/resolve?secid=${encoded}`;

    let data: Record<string, unknown>;
    try {
      const resp = await fetch(url, {
        headers: {
          Accept: "application/json",
          "User-Agent": "secid-typescript-client/1.0",
        },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      const contentLength = resp.headers.get("content-length");
      if (contentLength && parseInt(contentLength, 10) > MAX_RESPONSE_BYTES) {
        return new SecIDResponse({
          secid_query: secid,
          status: "error",
          results: [],
          message: `Response exceeds ${MAX_RESPONSE_BYTES} byte limit`,
        });
      }
      const body = await resp.text();
      if (body.length > MAX_RESPONSE_BYTES) {
        return new SecIDResponse({
          secid_query: secid,
          status: "error",
          results: [],
          message: `Response exceeds ${MAX_RESPONSE_BYTES} byte limit`,
        });
      }
      data = JSON.parse(body) as Record<string, unknown>;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const prefix = err instanceof DOMException && err.name === "TimeoutError"
        ? "Request timed out"
        : "Connection error";
      return new SecIDResponse({
        secid_query: secid,
        status: "error",
        results: [],
        message: `${prefix}: ${msg}`,
      });
    }

    return new SecIDResponse({
      secid_query: (data.secid_query as string) ?? secid,
      status: (data.status as string) ?? "error",
      results: (data.results as SecIDResult[]) ?? [],
      message: data.message as string | undefined,
    });
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
   * @param type - SecID type (advisory, weakness, ttp, control, regulation, entity, reference).
   * @param identifier - The identifier to search for, e.g. "CVE-2021-44228".
   */
  async lookup(type: string, identifier: string): Promise<SecIDResponse> {
    return this.resolve(`secid:${type}/${identifier}`);
  }
}
