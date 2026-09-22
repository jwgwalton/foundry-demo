FROM python:3.12-slim

# Copy uv from the official image so dependency installation is lockfile-driven.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

# Run the local dependency service as an unprivileged user.
RUN groupadd --gid 10001 app && \
	useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app && \
	install -d --owner app --group app /app

WORKDIR /app

# Install the locked runtime dependencies in a cacheable layer.
COPY --chown=app:app pyproject.toml uv.lock ./
USER app
RUN uv sync --locked --no-dev --no-install-project --no-cache

# Copy application code after dependency installation so source changes remain cacheable.
COPY --chown=app:app src ./src
COPY --chown=app:app fixtures ./fixtures

ENV PATH="/app/.venv/bin:$PATH" \
	PYTHONPATH=/app/src \
	PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1
EXPOSE 8001

CMD ["uvicorn", "dummy_systems.business_api.app:app", "--host", "0.0.0.0", "--port", "8001"]