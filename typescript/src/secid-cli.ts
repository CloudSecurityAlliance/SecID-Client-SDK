#!/usr/bin/env node
/**
 * SecID CLI — resolve security identifiers to URLs.
 *
 * Usage:
 *     secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
 *     secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
 */

import { SecIDClient } from "./secid-client.js";

/** Strip C0/C1 control chars (incl. ESC) from server-controlled text before
 * printing to a terminal — prevents ANSI/escape-sequence injection. */
function sanitizeTerminal(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/[\u0000-\u001F\u007F-\u009F]/g, "");
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes("-h") || args.includes("--help")) {
    console.log("Usage: secid [--json] <secid>");
    console.log();
    console.log("Examples:");
    console.log('  secid "secid:advisory/mitre.org/cve#CVE-2021-44228"');
    console.log('  secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"');
    console.log('  secid "secid:advisory/CVE-2021-44228"');
    process.exit(0);
  }

  const jsonMode = args.includes("--json");
  const secid = args.filter((a: string) => a !== "--json")[0];
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
        const first = response.results[0];
        const corrected = first && "secid" in first ? first.secid : "";
        console.error(`(corrected to: ${sanitizeTerminal(String(corrected))})`);
      }
      console.log(sanitizeTerminal(url));
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
    console.error(`${response.status}: ${sanitizeTerminal(msg)}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
