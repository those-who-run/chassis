// Command chassis runs the template's example service: it reads its configuration
// from the environment, logs JSON to standard output and serves GET /healthz until
// it gets SIGINT or SIGTERM. `chassis -version` prints its version and exits.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"

	"github.com/those-who-run/chassis/internal/service"
)

// version is the build's version, set with -ldflags "-X main.version=X.Y.Z"; a
// published image also carries it in its org.opencontainers.image.version label.
var version = "dev"

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Getenv, os.Stdout, os.Stderr))
}

// run is main without the process around it, so the tests can call it. It serves
// until ctx is done or the process gets SIGINT or SIGTERM, and returns the exit
// code: 0 after a clean shutdown, 1 when the service fails, 2 for a bad flag or
// configuration.
func run(ctx context.Context, args []string, getenv func(string) string, stdout, stderr io.Writer) int {
	ctx, stop := signal.NotifyContext(ctx, os.Interrupt, syscall.SIGTERM)
	defer stop()
	flags := flag.NewFlagSet("chassis", flag.ContinueOnError)
	flags.SetOutput(stderr)
	showVersion := flags.Bool("version", false, "print the version and exit")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *showVersion {
		_, _ = fmt.Fprintln(stdout, version)
		return 0
	}
	cfg, err := service.ConfigFromEnv(getenv)
	if err != nil {
		_, _ = fmt.Fprintln(stderr, err)
		return 2
	}
	log := service.NewLogger(stdout, cfg.LogLevel)
	if err := service.Run(ctx, cfg, log, version); err != nil {
		log.ErrorContext(ctx, "stopped", "err", err)
		return 1
	}
	return 0
}
