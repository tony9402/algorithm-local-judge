UV ?= uv
UV_CACHE_DIR ?= .uv-cache
PYTHON ?= UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python
RUFF ?= UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run ruff
PLATFORM ?=

JUDGE := $(PYTHON) -m judge

.DEFAULT_GOAL := help

.PHONY: help all web test e2e e2e-judge e2e-judge-cli e2e-judge-web \
	e2e-judge-pack e2e-problem-studio e2e-install lint format-check smoke \
	package-smoke-problem-studio packaged-web-smoke release-ready cache-status \
	cache-clear cache-clear-dry pack-verify pack-list build-standalone \
	release-check testlib-check clean

help:
	@echo "Repository targets:"
	@echo "  make web                         Start local web UI"
	@echo "  make test                        Run Python smoke tests"
	@echo "  make e2e                         Run browser E2E tests"
	@echo "  make e2e-judge                   Run judge CLI, pack, and web E2E tests"
	@echo "  make e2e-judge-cli               Run judge CLI E2E tests"
	@echo "  make e2e-judge-web               Run judge browser E2E tests"
	@echo "  make e2e-judge-pack              Run judge pack/source install E2E tests"
	@echo "  make e2e-problem-studio          Run Problem Studio browser E2E tests"
	@echo "  make e2e-install                 Install Playwright Chromium"
	@echo "  make lint                        Run ruff lint"
	@echo "  make format-check                Check ruff formatting"
	@echo "  make smoke                       Run lint, format-check, tests, and testlib check"
	@echo "  make package-smoke-problem-studio Build/install smoke for Problem Studio"
	@echo "  make packaged-web-smoke          Build/install smoke for packaged judge Web"
	@echo "  make release-ready               Run local release readiness checks"
	@echo "  make cache-status                Show cache status"
	@echo "  make cache-clear-dry             Preview cache clear"
	@echo "  make cache-clear                 Clear all cache with explicit --yes"
	@echo "  make pack-verify PACK=path       Verify a problem pack"
	@echo "  make pack-list                   List installed problem packs"
	@echo "  make build-standalone            Build Nuitka standalone tar.gz"
	@echo "  make release-check               Scan release artifacts"
	@echo "  make testlib-check               Ensure common testlib.h exists"
	@echo "  make clean                       Remove repository build outputs"
	@echo ""
	@echo "Problem authoring targets live in problems/Makefile:"
	@echo "  make -C problems help"
	@echo "  make -C problems testlib-link"
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

e2e:
	$(PYTHON) -m unittest discover tests/e2e -p 'e2e_*.py' -v

e2e-judge: e2e-judge-cli e2e-judge-pack e2e-judge-web

e2e-judge-cli:
	$(PYTHON) -m unittest tests.e2e.e2e_judge_cli -v

e2e-judge-pack:
	$(PYTHON) -m unittest tests.e2e.e2e_judge_pack_install -v

e2e-judge-web:
	$(PYTHON) -m unittest tests.e2e.e2e_judge_web -v

e2e-problem-studio:
	$(PYTHON) -m unittest tests.e2e.e2e_problem_studio -v

e2e-install:
	$(PYTHON) -m playwright install chromium

lint:
	$(RUFF) check .

format-check:
	$(RUFF) format --check .

smoke: lint format-check test testlib-check

package-smoke-problem-studio:
	$(PYTHON) scripts/smoke_problem_studio_package.py

packaged-web-smoke:
	$(PYTHON) scripts/smoke_judge_web_package.py

release-ready: lint format-check test e2e-judge e2e-problem-studio package-smoke-problem-studio packaged-web-smoke

cache-status:
	$(JUDGE) cache status

cache-clear-dry:
	$(JUDGE) cache clear --all --dry-run

cache-clear:
	$(JUDGE) cache clear --all --yes

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
