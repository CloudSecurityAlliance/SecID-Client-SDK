// Package secid provides a client for the SecID resolve API.
//
// SecID is a universal grammar for security knowledge:
//
//	secid:type/namespace/name[@version]#subpath
//
// API: GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded}
//
// IMPORTANT: The # character in SecID strings must be encoded as %23 in the
// URL query parameter. This is the #1 failure mode for new clients.
//
// Usage as library:
//
//	client := secid.NewClient("")
//	resp, err := client.Resolve("secid:advisory/mitre.org/cve#CVE-2021-44228")
//	fmt.Println(resp.BestURL())
//
// Usage as CLI:
//
//	go run secid.go "secid:advisory/mitre.org/cve#CVE-2021-44228"
//	go run secid.go --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
)

const DefaultBaseURL = "https://secid.cloudsecurityalliance.org"
const DefaultTimeout = 30 * time.Second
const MaxResponseBytes = 10 * 1024 * 1024 // 10 MB

// Response is the envelope returned by the SecID resolve API.
type Response struct {
	// SecIDQuery is the query string echoed back (decoded form).
	SecIDQuery string `json:"secid_query"`
	// Status is one of: found, corrected, related, not_found, error.
	Status string `json:"status"`
	// Results contains resolution or registry result objects.
	Results []Result `json:"results"`
	// Message provides guidance on not_found/error, empty otherwise.
	Message string `json:"message,omitempty"`
}

// Result is a single item in the results array.
// Check HasWeight() to determine if this is a resolution result (weight + url)
// or a registry result (data).
type Result struct {
	SecID  string                 `json:"secid"`
	Weight *int                   `json:"weight,omitempty"`
	URL    string                 `json:"url,omitempty"`
	Data   map[string]interface{} `json:"data,omitempty"`
}

// HasWeight returns true if this is a resolution result (has weight + url).
func (r Result) HasWeight() bool {
	return r.Weight != nil
}

// BestURL returns the highest-weight URL from resolution results, or empty string.
func (r *Response) BestURL() string {
	resolved := r.ResolutionResults()
	if len(resolved) == 0 {
		return ""
	}
	return resolved[0].URL
}

// WasCorrected returns true if the server corrected the input.
func (r *Response) WasCorrected() bool {
	return r.Status == "corrected"
}

// ResolutionResults returns only results with weight + url, sorted by weight descending.
func (r *Response) ResolutionResults() []Result {
	var resolved []Result
	for _, res := range r.Results {
		if res.HasWeight() && res.URL != "" {
			resolved = append(resolved, res)
		}
	}
	sort.Slice(resolved, func(i, j int) bool {
		return *resolved[i].Weight > *resolved[j].Weight
	})
	return resolved
}

// RegistryResults returns only results with data (registry/browsing info).
func (r *Response) RegistryResults() []Result {
	var registry []Result
	for _, res := range r.Results {
		if res.Data != nil {
			registry = append(registry, res)
		}
	}
	return registry
}

// Client is an HTTP client for the SecID resolve API.
type Client struct {
	BaseURL    string
	HTTPClient *http.Client
}

// NewClient creates a new SecID client. Pass empty string for the default base URL.
func NewClient(baseURL string) *Client {
	if baseURL == "" {
		baseURL = DefaultBaseURL
	}
	return &Client{
		BaseURL:    strings.TrimRight(baseURL, "/"),
		HTTPClient: &http.Client{Timeout: DefaultTimeout},
	}
}

// Resolve resolves a SecID string to URL(s).
// The # character is automatically encoded as %23 in the query parameter.
func (c *Client) Resolve(secid string) (*Response, error) {
	encoded := strings.ReplaceAll(secid, "#", "%23")
	url := fmt.Sprintf("%s/api/v1/resolve?secid=%s", c.BaseURL, encoded)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("building request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "secid-go-client/1.0")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	limited := io.LimitReader(resp.Body, MaxResponseBytes+1)
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("reading response: %w", err)
	}
	if len(body) > MaxResponseBytes {
		return nil, fmt.Errorf("response exceeds %d byte limit", MaxResponseBytes)
	}

	var result Response
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parsing response: %w", err)
	}
	return &result, nil
}

// BestURL resolves a SecID and returns the highest-weight URL, or empty string.
func (c *Client) BestURL(secid string) (string, error) {
	resp, err := c.Resolve(secid)
	if err != nil {
		return "", err
	}
	return resp.BestURL(), nil
}

// Lookup performs a cross-source search: finds an identifier across all sources of a type.
// typ is a SecID type (advisory, weakness, ttp, control, capability, methodology, disclosure, regulation, entity, reference).
// Equivalent to Resolve(fmt.Sprintf("secid:%s/%s", typ, identifier)).
func (c *Client) Lookup(typ, identifier string) (*Response, error) {
	return c.Resolve(fmt.Sprintf("secid:%s/%s", typ, identifier))
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
	var secid string
	for _, arg := range os.Args[1:] {
		if arg == "--json" {
			jsonMode = true
		} else if secid == "" {
			secid = arg
		}
	}
	if secid == "" {
		fmt.Fprintln(os.Stderr, "Error: no SecID provided")
		os.Exit(1)
	}

	client := NewClient("")
	resp, err := client.Resolve(secid)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
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
				fmt.Fprintf(os.Stderr, "(corrected to: %s)\n", resp.Results[0].SecID)
			}
			fmt.Println(url)
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
		fmt.Fprintf(os.Stderr, "%s: %s\n", resp.Status, msg)
		os.Exit(1)
	}
}
