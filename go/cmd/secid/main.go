// Command secid resolves a SecID string to a URL using the SecID resolve API.
//
// Usage:
//
//	secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
//	secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
//
// Install:
//
//	go install github.com/CloudSecurityAlliance/SecID-Client-SDK/go/cmd/secid@latest
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	secid "github.com/CloudSecurityAlliance/SecID-Client-SDK/go"
)

// sanitizeTerminal strips C0/C1 control chars (incl. ESC) from server-controlled
// text before printing — prevents ANSI/escape-sequence injection.
func sanitizeTerminal(s string) string {
	return strings.Map(func(r rune) rune {
		if r < 0x20 || r == 0x7f || (r >= 0x80 && r <= 0x9f) {
			return -1
		}
		return r
	}, s)
}

func main() {
	if len(os.Args) < 2 || os.Args[1] == "-h" || os.Args[1] == "--help" {
		fmt.Println("Usage: secid [--json] <secid>")
		fmt.Println()
		fmt.Println("Examples:")
		fmt.Println(`  secid "secid:advisory/mitre.org/cve#CVE-2021-44228"`)
		fmt.Println(`  secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"`)
		fmt.Println(`  secid "secid:advisory/CVE-2021-44228"`)
		os.Exit(0)
	}

	jsonMode := false
	var query string
	for _, arg := range os.Args[1:] {
		if arg == "--json" {
			jsonMode = true
		} else if query == "" {
			query = arg
		}
	}
	if query == "" {
		fmt.Fprintln(os.Stderr, "Error: no SecID provided")
		os.Exit(1)
	}

	client := secid.NewClient("")
	resp, err := client.Resolve(query)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %s\n", sanitizeTerminal(err.Error()))
		os.Exit(1)
	}

	if jsonMode {
		out, _ := json.MarshalIndent(resp, "", "  ")
		fmt.Println(string(out))
		return
	}

	switch resp.Status {
	case "found", "corrected":
		url := resp.BestURL()
		if url != "" {
			if resp.WasCorrected() && len(resp.Results) > 0 {
				fmt.Fprintf(os.Stderr, "(corrected to: %s)\n", sanitizeTerminal(resp.Results[0].SecID))
			}
			fmt.Println(sanitizeTerminal(url))
		} else {
			for _, r := range resp.RegistryResults() {
				out, _ := json.MarshalIndent(r, "", "  ")
				fmt.Println(string(out))
			}
		}
	case "related":
		for _, r := range resp.Results {
			out, _ := json.MarshalIndent(r, "", "  ")
			fmt.Println(string(out))
		}
	default:
		msg := resp.Message
		if msg == "" {
			msg = "No results"
		}
		fmt.Fprintf(os.Stderr, "%s: %s\n", sanitizeTerminal(resp.Status), sanitizeTerminal(msg))
		os.Exit(1)
	}
}
