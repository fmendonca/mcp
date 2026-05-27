FROM alpine:3.21

RUN apk add --no-cache python3 py3-pip && \
    adduser -D -u 1001 -g mcpuser mcpuser

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY main.py .

RUN chown -R mcpuser:mcpuser /app && \
    chmod -R u-w,g-rwx,o-rwx /app && \
    chmod u+r /app/main.py /app/requirements.txt

USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import sys; import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3); sys.exit(0)" || exit 1

LABEL org.opencontainers.image.source="https://github.com/fmendonca/mcp" \
      org.opencontainers.image.title="mcp-openshift" \
      org.opencontainers.image.description="OpenShift Admin MCP Server" \
      org.opencontainers.image.version="0.3.1"

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
