UV ?= uv
UV_CACHE_DIR ?= .uv-cache
PYTHON ?= UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python
RUFF ?= UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run ruff
PLATFORM ?=

JUDGE := $(PYTHON) -m judge

.DEFAULT_GOAL := help

.PHONY: help all web test lint format-check smoke cache-status cache-clear cache-clear-dry pack-verify pack-list build-standalone release-check testlib-check clean

help:
	@echo "Repository targets:"
	@echo "  make web                         Start local web UI"
	@echo "  make test                        Run Python smoke tests"
	@echo "  make lint                        Run ruff lint"
	@echo "  make format-check                Check ruff formatting"
	@echo "  make smoke                       Run lint, format-check, tests, and testlib check"
	@echo "  make cache-status                Show cache status"
	@echo "  make cache-clear-dry             Preview cache clear"
	@echo "  make cache-clear                 Clear all cache with confirmation"
	@echo "  make pack-verify PACK=path       Verify a problem pack"
	@echo "  make pack-list                   List installed problem packs"
	@echo "  make build-standalone            Build Nuitka standalone tar.gz"
	@echo "  make release-check               Scan release artifacts"
	@echo "  make testlib-check               Ensure common testlib.h exists"
	@echo "  make clean                       Remove repository build outputs"
	@echo ""
	@echo "Problem authoring targets live in problems/Makefile:"
	@echo "  make -C problems help"
	@echo "  make -C problems build-pack PROBLEM=06 PACK_ID=basic"
	@echo ""
	@echo "Examples:"
	@echo "  make lint"
	@echo "  make build-standalone PLATFORM=macos-arm64"

all: lint test testlib-check

web:
	$(JUDGE) web

test:
	$(PYTHON) -m unittest -v

lint:
	$(RUFF) check .

format-check:
	$(RUFF) format --check .

smoke: lint format-check test testlib-check

cache-status:
	$(JUDGE) cache status

cache-clear-dry:
	$(JUDGE) cache clear --all --dry-run

cache-clear:
	$(JUDGE) cache clear --all

pack-verify:
	$(JUDGE) pack verify $(PACK)

pack-list:
	$(JUDGE) pack list

build-standalone:
	$(PYTHON) scripts/build_standalone.py $(if $(PLATFORM),--platform $(PLATFORM),)

release-check:
	$(PYTHON) scripts/scan_release_artifact.py

testlib-check:
	test -f testlib.h

clean:
	rm -rf build
