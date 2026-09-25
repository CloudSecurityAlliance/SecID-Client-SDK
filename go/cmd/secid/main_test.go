package main

import "testing"

func TestSanitizeTerminal(t *testing.T) {
	if got := sanitizeTerminal("https://x/\x1b[2Jfake"); got != "https://x/[2Jfake" {
		t.Errorf("sanitizeTerminal stripped wrong: %q", got)
	}
	if got := sanitizeTerminal("plain text"); got != "plain text" {
		t.Errorf("sanitizeTerminal changed plain text: %q", got)
	}
}
