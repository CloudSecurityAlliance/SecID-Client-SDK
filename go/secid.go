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
//	import "github.com/CloudSecurityAlliance/SecID-Client-SDK/go"
//
//	client := secid.NewClient("")
//	resp, err := client.Resolve("secid:advisory/mitre.org/cve#CVE-2021-44228")
//	fmt.Println(resp.BestURL())
//
// The CLI lives in the cmd/secid subdirectory:
//
//	go run ./cmd/secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
//	go run ./cmd/secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
package secid

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
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
//
// Decoding is deliberately tolerant: the resolver response is untrusted, so a
// field with an unexpected JSON type (a string weight, a numeric url) is left
// at its zero value instead of rejecting the whole response. Weight is a float
// because the API contract only promises a number, not an integer.
type Result struct {
	SecID             string                 `json:"secid"`
	Weight            *float64               `json:"weight,omitempty"`
	URL               string                 `json:"url,omitempty"`
	ContentType       string                 `json:"content_type,omitempty"`         // MIME type
	Parsability       string                 `json:"parsability,omitempty"`          // "structured" or "scraped"
	Schema            string                 `json:"schema,omitempty"`               // SecID reference to data schema
	ParseInstructions string                 `json:"parsing_instructions,omitempty"` // SecID reference to parsing doc
	Auth              string                 `json:"auth,omitempty"`                 // Free-text auth description
	Data              map[string]interface{} `json:"data,omitempty"`
}

// HasWeight returns true if this is a resolution result (has weight + url).
func (r Result) HasWeight() bool {
	return r.Weight != nil
}

// UnmarshalJSON decodes a result object field by field, ignoring fields whose
// JSON type does not match. A non-object element is an error; Response
// decoding skips such elements rather than failing.
func (r *Result) UnmarshalJSON(b []byte) error {
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(b, &raw); err != nil {
		return err
	}
	if raw == nil {
		return errors.New("result is not a JSON object")
	}
	*r = Result{}
	str := func(key string) string {
		var s string
		if v, ok := raw[key]; ok && json.Unmarshal(v, &s) == nil {
			return s
		}
		return ""
	}
	r.SecID = str("secid")
	r.URL = str("url")
	r.ContentType = str("content_type")
	r.Parsability = str("parsability")
	r.Schema = str("schema")
	r.ParseInstructions = str("parsing_instructions")
	r.Auth = str("auth")
	if v, ok := raw["weight"]; ok {
		var w float64
		if json.Unmarshal(v, &w) == nil && !bytes.Equal(bytes.TrimSpace(v), []byte("null")) {
			r.Weight = &w
		}
	}
	if v, ok := raw["data"]; ok {
		var d map[string]interface{}
		if json.Unmarshal(v, &d) == nil && d != nil {
			r.Data = d
		}
	}
	return nil
}

// UnmarshalJSON decodes the envelope tolerantly: results that are not JSON
// objects are skipped, and a non-array "results" value yields no results. The
// envelope itself must be a JSON object; Resolve reports anything else as an
// error.
func (r *Response) UnmarshalJSON(b []byte) error {
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(b, &raw); err != nil {
		return err
	}
	if raw == nil {
		return errors.New("response is not a JSON object")
	}
	*r = Response{}
	str := func(key string) string {
		var s string
		if v, ok := raw[key]; ok && json.Unmarshal(v, &s) == nil {
			return s
		}
		return ""
	}
	r.SecIDQuery = str("secid_query")
	r.Status = str("status")
	r.Message = str("message")
	var items []json.RawMessage
	if v, ok := raw["results"]; ok && json.Unmarshal(v, &items) == nil {
		for _, item := range items {
			var res Result
			if json.Unmarshal(item, &res) == nil {
				r.Results = append(r.Results, res)
			}
		}
	}
	return nil
}

// allowedURLSchemes — the resolver response is untrusted (a hostile, federated,
// or MITM'd resolver is in scope); only http(s) URLs may be surfaced as a best URL.
var allowedURLSchemes = map[string]bool{"https": true, "http": true}

// validateURL returns u only if it is an absolute http(s) URL, else "".
func validateURL(u string) string {
	if u == "" {
		return ""
	}
	parsed, err := url.Parse(u)
	if err != nil || !allowedURLSchemes[strings.ToLower(parsed.Scheme)] || parsed.Host == "" {
		return ""
	}
	return u
}

// BestURL returns the highest-weight URL from resolution results, or empty string.
// The URL is scheme-validated (http/https only) before being returned.
func (r *Response) BestURL() string {
	resolved := r.ResolutionResults()
	if len(resolved) == 0 {
		return ""
	}
	return validateURL(resolved[0].URL)
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
	sort.SliceStable(resolved, func(i, j int) bool {
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
	encoded := url.QueryEscape(secid)
	reqURL := fmt.Sprintf("%s/api/v1/resolve?secid=%s", c.BaseURL, encoded)

	req, err := http.NewRequest("GET", reqURL, nil)
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

	// Anything but a JSON object (null, [], a bare string) is not a SecID
	// envelope. Reject it here instead of returning a Response with an empty
	// Status that callers would mistake for a real answer.
	trimmed := bytes.TrimSpace(body)
	if len(trimmed) == 0 || trimmed[0] != '{' {
		return nil, fmt.Errorf("parsing response: expected a JSON object, got %.40q", trimmed)
	}
	var result Response
	if err := json.Unmarshal(trimmed, &result); err != nil {
		return nil, fmt.Errorf("parsing response: %w", err)
	}
	if result.Status == "" {
		result.Status = "error"
		if result.Message == "" {
			result.Message = "Response has no status field"
		}
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
