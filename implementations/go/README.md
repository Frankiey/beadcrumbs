# Go client

The command entry point lives in cmd/beadcrumbs. Internal tracker code separates Codec, logical validation, store publication, lifecycle, and board rendering. It uses only the Go standard library.

From the repository root with Go 1.22+

```sh
GOPROXY=off go -C implementations/go test ./...
GOPROXY=off go -C implementations/go build -o bin/beadcrumbs ./cmd/beadcrumbs
implementations/go/bin/beadcrumbs --help
```

Native tests exercise strict JSON, an alternate codec through the lifecycle, and failed publication cleanup. The built executable has no Python or Go runtime installation requirement. bin/ and .cache/ are ignored.

Verified locally with Go 1.27.4 on macOS. Other supported toolchains and operating systems still need verification.
