package main

import (
	"beadcrumbs.local/go/internal/tracker"
	"os"
)

func main() { os.Exit(tracker.Main(os.Args[1:])) }
