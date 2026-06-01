FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/algorithm-local-judge/venv/bin:${PATH}" \
    ALJ_PROJECT_ROOT=/app \
    JUDGE_SOURCE_ROOT=/app \
    ALJ_DATA_HOME=/data \
    ALJ_CACHE_HOME=/data/cache

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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md THIRD_PARTY_NOTICES.md ./
COPY commons ./commons
COPY judge ./judge
COPY problem_studio ./problem_studio
COPY testlib.h ./testlib.h

RUN python3 -m venv /opt/algorithm-local-judge/venv \
    && /opt/algorithm-local-judge/venv/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/algorithm-local-judge/venv/bin/pip install --no-cache-dir .

RUN useradd --create-home --shell /bin/bash alj \
    && mkdir -p /data/cache /data/problem-packs /data/problem-sources /workspace \
    && chown -R alj:alj /data /workspace /app

USER alj
WORKDIR /workspace

VOLUME ["/data", "/workspace"]
EXPOSE 8765 8775

CMD ["judge", "web", "--host", "0.0.0.0", "--no-open", "--allow-remote-run"]
