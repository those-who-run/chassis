package main

import (
	"bytes"
	"context"
	"strings"
	"testing"
	"time"
)

func env(vars map[string]string) func(string) string {
	return func(key string) string { return vars[key] }
}

func TestVersion(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := run(t.Context(), []string{"-version"}, env(nil), &stdout, &stderr); code != 0 {
		t.Fatalf("exit %d, stderr %q", code, stderr.String())
	}
	if got := strings.TrimSpace(stdout.String()); got != version {
		t.Errorf("printed %q, want %q", got, version)
	}
}

func TestAnUnknownFlagIsAUsageError(t *testing.T) {
	var stderr bytes.Buffer
	if code := run(t.Context(), []string{"-nope"}, env(nil), &bytes.Buffer{}, &stderr); code != 2 {
		t.Errorf("exit %d, want 2", code)
	}
	if !strings.Contains(stderr.String(), "-nope") {
		t.Errorf("stderr %q does not name the flag", stderr.String())
	}
}

func TestABadConfigurationIsAUsageError(t *testing.T) {
	var stderr bytes.Buffer
	code := run(t.Context(), nil, env(map[string]string{"LOG_LEVEL": "loud"}), &bytes.Buffer{}, &stderr)
	if code != 2 || !strings.Contains(stderr.String(), "LOG_LEVEL") {
		t.Errorf("exit %d, stderr %q; want 2 and LOG_LEVEL named", code, stderr.String())
	}
}

func TestAServiceThatCannotStartExitsOne(t *testing.T) {
	var stdout bytes.Buffer
	code := run(t.Context(), nil, env(map[string]string{"ADDR": "256.0.0.1:0"}), &stdout, &bytes.Buffer{})
	if code != 1 || !strings.Contains(stdout.String(), `"msg":"stopped"`) {
		t.Errorf("exit %d, log %q; want 1 and the failure logged", code, stdout.String())
	}
}

func TestServesUntilCancelled(t *testing.T) {
	ctx, cancel := context.WithTimeout(t.Context(), 100*time.Millisecond)
	defer cancel()
	var stdout bytes.Buffer
	code := run(ctx, nil, env(map[string]string{"ADDR": "127.0.0.1:0"}), &stdout, &bytes.Buffer{})
	if code != 0 || !strings.Contains(stdout.String(), `"msg":"serving"`) {
		t.Errorf("exit %d, log %q; want 0 and serving logged", code, stdout.String())
	}
}
