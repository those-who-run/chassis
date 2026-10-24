package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func env(vars map[string]string) func(string) string {
	return func(key string) string { return vars[key] }
}

func TestConfigFromEnv(t *testing.T) {
	for _, c := range []struct {
		name string
		vars map[string]string
		want Config
	}{
		{"defaults", nil, Config{Addr: ":8080", LogLevel: slog.LevelInfo}},
		{"set", map[string]string{"ADDR": "127.0.0.1:9000", "LOG_LEVEL": "debug"},
			Config{Addr: "127.0.0.1:9000", LogLevel: slog.LevelDebug}},
		{"upper case level", map[string]string{"LOG_LEVEL": "WARN"},
			Config{Addr: ":8080", LogLevel: slog.LevelWarn}},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := ConfigFromEnv(env(c.vars))
			if err != nil || got != c.want {
				t.Errorf("ConfigFromEnv = %+v, %v; want %+v, nil", got, err, c.want)
			}
		})
	}
}

func TestConfigFromEnvRefusesAnUnknownLevel(t *testing.T) {
	_, err := ConfigFromEnv(env(map[string]string{"LOG_LEVEL": "loud"}))
	if err == nil || !strings.HasPrefix(err.Error(), "LOG_LEVEL: ") {
		t.Errorf("ConfigFromEnv(LOG_LEVEL=loud) error = %v, want one naming LOG_LEVEL", err)
	}
}

func TestNewLoggerWritesJSONFromItsLevel(t *testing.T) {
	var buf bytes.Buffer
	log := NewLogger(&buf, slog.LevelWarn)
	log.Info("dropped")
	log.Warn("kept", "lap", 3)

	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) != 1 {
		t.Fatalf("got %d lines, want 1: %q", len(lines), buf.String())
	}
	var record map[string]any
	if err := json.Unmarshal([]byte(lines[0]), &record); err != nil {
		t.Fatalf("not JSON: %v: %q", err, lines[0])
	}
	if record["msg"] != "kept" || record["level"] != "WARN" || record["lap"] != float64(3) {
		t.Errorf("record = %v", record)
	}
}

func TestHealthz(t *testing.T) {
	rec := httptest.NewRecorder()
	Handler("1.2.3").ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/healthz", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q", ct)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "ok" || body["version"] != "1.2.3" {
		t.Errorf("body = %v", body)
	}
}

func TestHealthzIsGetOnly(t *testing.T) {
	rec := httptest.NewRecorder()
	Handler("1.2.3").ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/healthz", nil))
	if rec.Code != http.StatusMethodNotAllowed {
		t.Errorf("POST /healthz status = %d, want 405", rec.Code)
	}
}

func TestRunServesUntilCancelled(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(t.Context())
	var logs bytes.Buffer
	done := make(chan error, 1)
	go func() { done <- serve(ctx, ln, NewLogger(&logs, slog.LevelInfo), "test") }()

	req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "http://"+ln.Addr().String()+"/healthz", nil)
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = io.Copy(io.Discard, resp.Body)
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("GET /healthz status = %d", resp.StatusCode)
	}

	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Errorf("serve returned %v after cancel, want nil", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("serve did not return after cancel")
	}
	if !strings.Contains(logs.String(), `"msg":"shutting down"`) {
		t.Errorf("no shutdown logged: %s", logs.String())
	}
}

func TestRunReportsAnAddressItCannotListenOn(t *testing.T) {
	err := Run(t.Context(), Config{Addr: "256.0.0.1:0"}, NewLogger(io.Discard, slog.LevelInfo), "test")
	if err == nil || !strings.HasPrefix(err.Error(), "listen: ") {
		t.Errorf("Run error = %v, want a listen error", err)
	}
}

func TestRunListensOnTheConfiguredAddress(t *testing.T) {
	// Cancelled once Run is serving: a context cancelled before it would stop the
	// listen itself.
	ctx, cancel := context.WithTimeout(t.Context(), 100*time.Millisecond)
	defer cancel()
	err := Run(ctx, Config{Addr: "127.0.0.1:0"}, NewLogger(io.Discard, slog.LevelInfo), "test")
	if err != nil {
		t.Errorf("Run = %v, want nil", err)
	}
}

func TestServeReportsAListenerThatFails(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	_ = ln.Close() // Serve fails at once on a closed listener
	err = serve(t.Context(), ln, NewLogger(io.Discard, slog.LevelInfo), "test")
	if err == nil || errors.Is(err, http.ErrServerClosed) {
		t.Errorf("serve on a closed listener = %v, want an error", err)
	}
}
