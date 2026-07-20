#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
PY="uv run --python 3.12 python"

# 최초 1회만 필요. 이미 설치되어 있으면 빠르게 넘어갑니다.
$PY -m playwright install chromium

# 정적/문법 확인
uv run ruff check .
uv run ruff format --check .
$PY -m py_compile \
  problem_studio/web/routes/jobs.py \
  problem_studio/web/routes/solutions.py \
  problem_studio/web/schemas.py

node --check problem_studio/web/static/app/actions/solutions.js
node --check problem_studio/web/static/app/jobs-view.js
node --check problem_studio/web/static/app/solution-status.js
node --check problem_studio/web/static/app/results.js

# Unit / functional
$PY -m unittest discover tests -p 'test_*.py' -v

# 기존 E2E 파일들
$PY -m unittest discover tests/e2e -p 'e2e_*.py' -v

# Problem Studio 분리 E2E
$PY -m unittest \
  tests.e2e.problem_studio_solution_tests \
  tests.e2e.problem_studio_authoring_tests \
  tests.e2e.problem_studio_build_tests \
  tests.e2e.problem_studio_git_tests \
  -v
