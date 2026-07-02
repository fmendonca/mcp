FROM alpine:3.21

# Single source of truth for the running app's self-reported version — set
# by CI to the actual tag/version being built (see build.sh). Never hardcode
# a version elsewhere; it drifts the moment nobody remembers to bump it.
ARG APP_VERSION=0.0.0-dev
ENV APP_VERSION=${APP_VERSION}

RUN apk add --no-cache \
    python3=3.12.13-r0 \
    py3-pip=24.3.1-r0 && \
    pip3 install --no-cache-dir --break-system-packages --upgrade 'pip>=26.1' 'setuptools>=78.1.1' && \
    adduser -D -u 1001 -g mcpuser mcpuser

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY *.py .

RUN chown -R mcpuser:0 /app && \
    chmod -R u=rwX,g=rX,o=rX /app

USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import sys; import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3); sys.exit(0)" || exit 1

LABEL org.opencontainers.image.source="https://github.com/fmendonca/mcp" \
      org.opencontainers.image.title="mcp-openshift" \
      org.opencontainers.image.description="OpenShift Admin MCP Server" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.created="2026-06-16T00:00:00Z"

CMD ["python3", "-m", "uvicorn", "--app-dir", "/app", "main:app", "--host", "0.0.0.0", "--port", "8000"]
