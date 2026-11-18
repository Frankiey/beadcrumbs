# Common development commands. CI runs these same targets.
# Run `make` or `make help` for the list.

PYTHON ?= python3
RUFF_VERSION ?= 0.17.5
# Use the pinned Ruff through uvx when available, otherwise a Ruff on PATH.
RUFF ?= $(if $(shell command -v uvx 2>/dev/null),uvx ruff@$(RUFF_VERSION),ruff)

# Offline-friendly defaults for local and air-gapped machines. CI clears these
# so dependencies can be fetched: make CARGO_NET= NPM_NET= ...
CARGO_NET ?= --offline
NPM_NET ?= --offline

GO_DIR := implementations/go
RUST_MANIFEST := implementations/rust/Cargo.toml
TS_DIR := implementations/javascript
DOTNET_SLN := implementations/dotnet/Beadcrumbs.sln
DOTNET_TESTS := implementations/dotnet/tests/Beadcrumbs.Tests

export GOPROXY ?= off
export DOTNET_CLI_TELEMETRY_OPTOUT := 1
export DOTNET_NOLOGO := 1
export DOTNET_GENERATE_ASPNET_CERTIFICATE := false
export PYTHONDONTWRITEBYTECODE := 1

.DEFAULT_GOAL := help
.PHONY: help check lint fmt test build matrix docs clean print-ruff-version \
	py-lint py-fmt py-test py-integration \
	go-lint go-fmt go-build go-test \
	rust-lint rust-fmt rust-build rust-test \
	ts-install ts-lint ts-build ts-test \
	dotnet-lint dotnet-fmt dotnet-build dotnet-test

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## ---- Everyday ----------------------------------------------------------

check: lint test docs ## Lint and test everything (what CI runs per client)

lint: py-lint go-lint rust-lint ts-lint dotnet-lint ## Lint and format-check every client

fmt: py-fmt go-fmt rust-fmt dotnet-fmt ## Auto-format every client

test: py-test go-test rust-test ts-test dotnet-test ## Run every client's own tests

build: go-build rust-build ts-build dotnet-build ## Build the Go, Rust, TypeScript, and .NET clients

matrix: build ## Run the shared CLI suite for all five clients and every client pair
	$(PYTHON) integration/test_clients.py

docs: ## Check Markdown links and anchors, and that JSON schemas and fixtures parse
	$(PYTHON) tools/check_docs.py

print-ruff-version:
	@echo $(RUFF_VERSION)

clean: ## Remove build outputs and generated integration runs
	rm -rf $(GO_DIR)/bin $(TS_DIR)/dist implementations/rust/target integration/.runs
	find implementations/dotnet -type d \( -name bin -o -name obj \) -prune -exec rm -rf {} +

## ---- Python (reference client) -----------------------------------------

py-lint: ## Ruff lint and format check
	$(RUFF) check .
	$(RUFF) format --check .

py-fmt: ## Ruff autofix and format
	$(RUFF) check --fix .
	$(RUFF) format .

py-test: ## Reference unittest suite
	$(PYTHON) -m unittest discover -s tests -v

py-integration: ## Persistent lifecycle example under integration/.runs
	$(PYTHON) integration/run.py

## ---- Go ----------------------------------------------------------------

go-lint: ## gofmt check and go vet
	@unformatted="$$(gofmt -l $(GO_DIR))"; \
	if [ -n "$$unformatted" ]; then echo "gofmt needed:"; echo "$$unformatted"; exit 1; fi
	go -C $(GO_DIR) vet ./...

go-fmt: ## gofmt in place
	gofmt -w $(GO_DIR)

go-build: ## Build implementations/go/bin/beadcrumbs
	go -C $(GO_DIR) build -o bin/beadcrumbs ./cmd/beadcrumbs

go-test: ## Go native tests
	go -C $(GO_DIR) test ./...

## ---- Rust --------------------------------------------------------------

rust-lint: ## rustfmt check and clippy with warnings as errors
	cargo fmt --check --manifest-path $(RUST_MANIFEST)
	cargo clippy $(CARGO_NET) --locked --manifest-path $(RUST_MANIFEST) --all-targets -- -D warnings

rust-fmt: ## rustfmt in place
	cargo fmt --manifest-path $(RUST_MANIFEST)

rust-build: ## Build implementations/rust/target/debug/beadcrumbs
	cargo build $(CARGO_NET) --locked --manifest-path $(RUST_MANIFEST)

rust-test: ## Rust native tests
	cargo test $(CARGO_NET) --locked --manifest-path $(RUST_MANIFEST)

## ---- TypeScript --------------------------------------------------------

$(TS_DIR)/node_modules: $(TS_DIR)/package-lock.json
	npm ci $(NPM_NET) --ignore-scripts --no-audit --no-fund --prefix $(TS_DIR)
	@touch $@

ts-install: $(TS_DIR)/node_modules ## Install pinned TypeScript build dependencies

ts-lint: ts-install ## Strict type check
	npm run lint --prefix $(TS_DIR)

ts-build: ts-install ## Compile to implementations/javascript/dist
	npm run build --prefix $(TS_DIR)

ts-test: ts-install ## Build and run TypeScript native tests
	npm test --prefix $(TS_DIR)

## ---- .NET --------------------------------------------------------------

dotnet-lint: ## dotnet format check (the build treats warnings as errors)
	dotnet format $(DOTNET_SLN) --verify-no-changes

dotnet-fmt: ## dotnet format in place
	dotnet format $(DOTNET_SLN)

dotnet-build: ## Build the CLI and test harness
	dotnet build $(DOTNET_SLN) --disable-build-servers

dotnet-test: dotnet-build ## .NET native tests
	dotnet run --project $(DOTNET_TESTS) --no-build
