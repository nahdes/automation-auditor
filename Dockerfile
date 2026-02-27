# ══════════════════════════════════════════════════════════════
#  Automaton Auditor — Dockerfile
#
#  Build:
#    docker build -t automaton-auditor .
#
#  Run a peer audit:
#    docker run --env-file .env automaton-auditor \
#      https://github.com/USER/repo.git \
#      /app/reports/final_report.pdf \
#      peer
#
#  Run a self-audit (mount output dir to retrieve the report):
#    docker run --env-file .env \
#      -v $(pwd)/audit:/app/audit \
#      automaton-auditor \
#      https://github.com/nahdes/automation-auditor.git \
#      /app/reports/final_report.pdf \
#      self
# ══════════════════════════════════════════════════════════════

# ── Stage 1: dependency builder ───────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# uv gives a fast, reproducible install from uv.lock
RUN pip install --no-cache-dir uv

# Copy manifests first — Docker caches this layer until they change
COPY pyproject.toml uv.lock ./

# Install all deps into an isolated venv inside /app/.venv
RUN uv sync --frozen --no-dev

# ── Stage 2: lean runtime image ───────────────────────────────
FROM python:3.11-slim AS runtime

# git is required by repo_tools.py for sandboxed cloning
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pull the pre-built venv from builder — no pip needed at runtime
COPY --from=builder /app/.venv /app/.venv

# Copy source and static assets
COPY src/    ./src/
COPY rubric/ ./rubric/
COPY reports/ ./reports/

# Ensure output directories exist so audit reports can be written
RUN mkdir -p \
    audit/report_onself_generated \
    audit/report_onpeer_generated \
    audit/report_bypeer_received \
    audit/langsmith_logs

# Activate the venv for all subsequent commands
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Sanity-check that the graph module imports cleanly
HEALTHCHECK --interval=30s --timeout=10s --retries=1 \
    CMD python -c "from src.graph import compile_graph; compile_graph(); print('OK')"

# argv: <repo_url> <pdf_path> <self|peer|received>
ENTRYPOINT ["python", "-m", "src.graph"]