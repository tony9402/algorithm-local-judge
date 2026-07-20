FROM ghcr.io/sigstore/cosign/cosign:v3.0.6@sha256:de9c65609e6bde17e6b48de485ee788407c9502fa08b8f4459f595b21f56cd00 AS cosign-bin

FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/algorithm-local-judge/venv/bin:${PATH}" \
    ALJ_PROJECT_ROOT=/app \
    JUDGE_SOURCE_ROOT=/app \
    ALJ_DATA_HOME=/data \
    ALJ_CACHE_HOME=/data/cache \
    ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS=30000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        openjdk-17-jdk-headless \
        python-is-python3 \
        python3 \
        python3-pip \
        python3-venv \
        pypy3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=cosign-bin /ko-app/cosign /usr/local/bin/cosign
COPY pyproject.toml README.md THIRD_PARTY_NOTICES.md ./
COPY alj_core ./alj_core
COPY commons ./commons
COPY judge ./judge
COPY problem_studio ./problem_studio
COPY testlib.h ./testlib.h

RUN python3 -m venv /opt/algorithm-local-judge/venv \
    && /opt/algorithm-local-judge/venv/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/algorithm-local-judge/venv/bin/pip install --no-cache-dir .

RUN groupadd --gid 10001 alj \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash alj \
    && mkdir -p /data/cache /data/jobs /data/problem-packs /data/problem-sources /workspace \
    && chown -R alj:alj /data /workspace /app

USER alj
WORKDIR /workspace

VOLUME ["/data"]
EXPOSE 8765 8775

CMD ["judge", "web", "--host", "0.0.0.0", "--no-open"]
