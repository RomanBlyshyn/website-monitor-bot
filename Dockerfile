FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# Headless Chromium is only needed for sources with `use_browser: true`.
ARG INSTALL_BROWSER=false
RUN if [ "$INSTALL_BROWSER" = "true" ]; then playwright install --with-deps chromium; fi

RUN useradd --create-home --uid 1000 monitor \
    && mkdir -p /data && chown monitor:monitor /data

COPY app ./app
# sources.yaml is optional; sources.example.yaml is the fallback.
COPY sources*.yaml ./

USER monitor
ENV DB_PATH=/data/monitor.db

CMD ["python", "-m", "app.main"]
