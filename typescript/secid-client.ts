#!/usr/bin/env -S npx tsx
/**
 * SecID client — resolve security identifiers to URLs.
 *
 * Single file, zero dependencies (fetch only). Copy and use.
 *
 * SecID is a universal grammar for security knowledge:
 *     secid:type/namespace/name[@version]#subpath
 *
 * API: GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded}
 *
 * IMPORTANT: The # character in SecID strings must be encoded as %23 in the
 * URL query parameter. This is the #1 failure mode for new clients.
 *
 * Usage as library:
 *     import { SecIDClient } from "./secid-client.ts";
 *     const client = new SecIDClient();
 *     const response = await client.resolve("secid:advisory/mitre.org/cve#CVE-2021-44228");
 *     console.log(response.bestUrl);
 *
 * Usage as CLI:
 *     npx tsx secid-client.ts "secid:advisory/mitre.org/cve#CVE-2021-44228"
 *     npx tsx secid-client.ts --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
 */

const DEFAULT_BASE_URL = "https://secid.cloudsecurityalliance.org";

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
    return (this.results as Record<string, unknown>[])
      .filter((r): r is ResolutionResult & Record<string, unknown> =>
        "weight" in r && "url" in r
      )
      .sort((a, b) => b.weight - a.weight);
  }

  /** Only results with data (registry/browsing info). */
  get registryResults(): RegistryResult[] {
    return (this.results as Record<string, unknown>[])
      .filter((r): r is RegistryResult & Record<string, unknown> => "data" in r);
  }
}

/** HTTP client for the SecID resolve API. */
export class SecIDClient {
  private readonly baseUrl: string;

  /**
   * @param baseUrl - API base URL. Defaults to the public SecID service.
   */
  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
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
      });
      data = (await resp.json()) as Record<string, unknown>;
    } catch (err) {
      return new SecIDResponse({
        secid_query: secid,
        status: "error",
        results: [],
        message: `Connection error: ${err instanceof Error ? err.message : String(err)}`,
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

// ── CLI ──

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes("-h") || args.includes("--help")) {
    console.log("Usage: secid-client.ts [--json] <secid>");
    console.log();
    console.log("Examples:");
    console.log('  secid-client.ts "secid:advisory/mitre.org/cve#CVE-2021-44228"');
    console.log('  secid-client.ts --json "secid:advisory/mitre.org/cve#CVE-2021-44228"');
    console.log('  secid-client.ts "secid:advisory/CVE-2021-44228"');
    process.exit(0);
  }

  const jsonMode = args.includes("--json");
  const secid = args.filter((a) => a !== "--json")[0];
  if (!secid) {
    console.error("Error: no SecID provided");
    process.exit(1);
  }

  const client = new SecIDClient();
  const response = await client.resolve(secid);

  if (jsonMode) {
    console.log(JSON.stringify({
      secid_query: response.secidQuery,
      status: response.status,
      results: response.results,
      message: response.message ?? null,
    }, null, 2));
  } else if (response.status === "found" || response.status === "corrected") {
    const url = response.bestUrl;
    if (url) {
      if (response.wasCorrected) {
        const corrected = (response.results[0] as Record<string, unknown>)?.secid ?? "";
        console.error(`(corrected to: ${corrected})`);
      }
      console.log(url);
    } else {
      for (const r of response.registryResults) {
        console.log(JSON.stringify(r, null, 2));
      }
    }
  } else if (response.status === "related") {
    for (const r of response.results) {
      console.log(JSON.stringify(r, null, 2));
    }
  } else {
    const msg = response.message ?? "No results";
    console.error(`${response.status}: ${msg}`);
    process.exit(1);
  }
}

// Run CLI if executed directly
const isMain =
  typeof process !== "undefined" &&
  process.argv[1] &&
  (process.argv[1].endsWith("secid-client.ts") ||
    process.argv[1].endsWith("secid-client.js"));

if (isMain) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
