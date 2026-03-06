package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// Fixture types
// ---------------------------------------------------------------------------

type FixtureFile struct {
	SuiteVersion string    `json:"suite_version"`
	Tests        []Fixture `json:"tests"`
}

type Fixture struct {
	Name         string          `json:"name"`
	Description  string          `json:"description"`
	Category     string          `json:"category"`
	Input        FixtureInput    `json:"input"`
	MockResponse MockResponse    `json:"mock_response"`
	Expected     FixtureExpected `json:"expected"`
}

type FixtureInput struct {
	SecID  string `json:"secid"`
	Method string `json:"method"`
}

type MockResponse struct {
	HTTPStatus    int              `json:"http_status"`
	Body          *json.RawMessage `json:"body,omitempty"`
	RawBody       *string          `json:"raw_body,omitempty"`
	ContentType   string           `json:"content_type,omitempty"`
	Behavior      string           `json:"behavior,omitempty"`
	BodySizeBytes int              `json:"body_size_bytes,omitempty"`
}

type FixtureExpected struct {
	Status               *string `json:"status,omitempty"`
	BestURL              *string `json:"best_url"` // pointer to distinguish null from absent
	WasCorrected         *bool   `json:"was_corrected,omitempty"`
	ResolutionResultCount *int   `json:"resolution_result_count,omitempty"`
	RegistryResultCount  *int    `json:"registry_result_count,omitempty"`
	Message              *string `json:"message"` // pointer to distinguish null from absent
	RaisesError          bool    `json:"raises_error,omitempty"`
	ErrorContains        string  `json:"error_contains,omitempty"`
	RequestURLContains   string  `json:"request_url_contains,omitempty"`
	RequestURLNotContains string  `json:"request_url_not_contains,omitempty"`
}

// ---------------------------------------------------------------------------
// Load fixtures
// ---------------------------------------------------------------------------

func loadFixtures(t *testing.T) []Fixture {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	dir := filepath.Dir(filename)
	path := filepath.Join(dir, "..", "tests", "fixtures.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("Failed to read fixtures: %v", err)
	}
	var ff FixtureFile
	if err := json.Unmarshal(data, &ff); err != nil {
		t.Fatalf("Failed to parse fixtures: %v", err)
	}
	return ff.Tests
}

// ---------------------------------------------------------------------------
// Mock server helpers
// ---------------------------------------------------------------------------

func createMockServer(t *testing.T, fixture Fixture, recordedURLs *[]string) *httptest.Server {
	t.Helper()
	mock := fixture.MockResponse

	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*recordedURLs = append(*recordedURLs, r.URL.String())

		if mock.Behavior == "timeout" {
			// Block until the client gives up
			time.Sleep(10 * time.Second)
			return
		}

		if mock.Behavior == "oversized_body" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			size := mock.BodySizeBytes
			if size == 0 {
				size = 11_000_000
			}
			w.Write(make([]byte, size))
			return
		}

		status := mock.HTTPStatus
		if status == 0 {
			status = 200
		}
		contentType := mock.ContentType
		if contentType == "" {
			contentType = "application/json"
		}

		w.Header().Set("Content-Type", contentType)
		w.WriteHeader(status)

		if mock.RawBody != nil {
			w.Write([]byte(*mock.RawBody))
		} else if mock.Body != nil {
			w.Write([]byte(*mock.Body))
		} else {
			w.Write([]byte("{}"))
		}
	}))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

func TestFixtures(t *testing.T) {
	fixtures := loadFixtures(t)

	for _, fixture := range fixtures {
		fixture := fixture // capture range variable
		t.Run(fixture.Name, func(t *testing.T) {
			if fixture.MockResponse.Behavior == "connection_refused" {
				testConnectionRefused(t, fixture)
				return
			}

			var recordedURLs []string
			server := createMockServer(t, fixture, &recordedURLs)
			defer server.Close()

			client := NewClient(server.URL)

			// Use short timeout for timeout tests
			if fixture.MockResponse.Behavior == "timeout" {
				client.HTTPClient.Timeout = 1 * time.Second
			} else {
				client.HTTPClient.Timeout = 5 * time.Second
			}

			if fixture.Expected.RaisesError {
				testErrorCase(t, client, fixture)
				return
			}

			resp, err := client.Resolve(fixture.Input.SecID)
			if err != nil {
				t.Fatalf("Unexpected error: %v", err)
			}

			assertExpected(t, fixture, resp, recordedURLs)
		})
	}
}

func testErrorCase(t *testing.T, client *Client, fixture Fixture) {
	t.Helper()
	resp, err := client.Resolve(fixture.Input.SecID)

	// Go client may return error OR a Response with status="error"
	if err != nil {
		// Error returned — that's valid for an error test
		if fixture.Expected.ErrorContains != "" {
			errLower := strings.ToLower(err.Error())
			if !strings.Contains(errLower, strings.ToLower(fixture.Expected.ErrorContains)) {
				t.Errorf("Expected error containing %q, got: %v", fixture.Expected.ErrorContains, err)
			}
		}
		return
	}

	// No error — response should have status="error"
	if resp.Status != "error" {
		t.Errorf("Expected error or status='error', got status=%q", resp.Status)
	}
}

func testConnectionRefused(t *testing.T, fixture Fixture) {
	t.Helper()
	// Point at a port where nothing is listening
	client := NewClient("http://127.0.0.1:1")
	client.HTTPClient.Timeout = 2 * time.Second

	resp, err := client.Resolve(fixture.Input.SecID)
	if err != nil {
		return // Error is expected
	}
	if resp.Status != "error" {
		t.Errorf("Expected error or status='error', got status=%q", resp.Status)
	}
}

func assertExpected(t *testing.T, fixture Fixture, resp *Response, recordedURLs []string) {
	t.Helper()
	exp := fixture.Expected

	if exp.Status != nil && resp.Status != *exp.Status {
		t.Errorf("status: expected %q, got %q", *exp.Status, resp.Status)
	}

	// BestURL: fixture null means "no URL" → Go's "" from BestURL()
	{
		actual := resp.BestURL()
		if exp.BestURL == nil {
			if actual != "" {
				t.Errorf("best_url: expected empty (null), got %q", actual)
			}
		} else if *exp.BestURL != actual {
			t.Errorf("best_url: expected %q, got %q", *exp.BestURL, actual)
		}
	}

	if exp.WasCorrected != nil {
		actual := resp.WasCorrected()
		if *exp.WasCorrected != actual {
			t.Errorf("was_corrected: expected %v, got %v", *exp.WasCorrected, actual)
		}
	}

	if exp.ResolutionResultCount != nil {
		actual := len(resp.ResolutionResults())
		if *exp.ResolutionResultCount != actual {
			t.Errorf("resolution_result_count: expected %d, got %d", *exp.ResolutionResultCount, actual)
		}
	}

	if exp.RegistryResultCount != nil {
		actual := len(resp.RegistryResults())
		if *exp.RegistryResultCount != actual {
			t.Errorf("registry_result_count: expected %d, got %d", *exp.RegistryResultCount, actual)
		}
	}

	// Message: fixture null means "no message" → Go's "" (string zero value)
	{
		if exp.Message == nil {
			if resp.Message != "" {
				t.Errorf("message: expected empty (null), got %q", resp.Message)
			}
		} else if *exp.Message != resp.Message {
			t.Errorf("message: expected %q, got %q", *exp.Message, resp.Message)
		}
	}

	if exp.RequestURLContains != "" {
		if len(recordedURLs) == 0 {
			t.Error("No request recorded")
		} else {
			url := recordedURLs[len(recordedURLs)-1]
			if !strings.Contains(url, exp.RequestURLContains) {
				t.Errorf("Request URL should contain %q, got: %s", exp.RequestURLContains, url)
			}
		}
	}

	if exp.RequestURLNotContains != "" {
		if len(recordedURLs) == 0 {
			t.Error("No request recorded")
		} else {
			url := recordedURLs[len(recordedURLs)-1]
			if strings.Contains(url, exp.RequestURLNotContains) {
				t.Errorf("Request URL should NOT contain %q, got: %s", exp.RequestURLNotContains, url)
			}
		}
	}
}

func intPtr(i int) *int       { return &i }
func strPtr(s string) *string { return &s }
func boolPtr(b bool) *bool    { return &b }

func TestFixturesLoaded(t *testing.T) {
	fixtures := loadFixtures(t)
	if len(fixtures) == 0 {
		t.Fatal("No fixtures loaded")
	}
	fmt.Printf("Loaded %d test fixtures\n", len(fixtures))
}
