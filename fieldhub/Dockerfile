# stage 1: install dependencies
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# stage 2: runtime
FROM python:3.12-slim
WORKDIR /app
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
EXPOSE 8443
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser
CMD ["sh", "-c", "\
    CERT=\"${FIELDHUB_TLS_CERT:-/certs/server.crt}\"; \
    KEY=\"${FIELDHUB_TLS_KEY:-/certs/server.key}\"; \
    if [ ! -f \"$CERT\" ] || [ ! -f \"$KEY\" ]; then \
        echo \"fieldhub: TLS cert/key not found at $CERT / $KEY - run scripts/field-hub/gen-certs.sh on the host first\" >&2; \
        exit 1; \
    fi; \
    exec uvicorn app.main:app --host 0.0.0.0 --port 8443 \
        --ssl-certfile \"$CERT\" --ssl-keyfile \"$KEY\""]
