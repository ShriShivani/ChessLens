# Build context is the repository root:  docker build -f server/Dockerfile .
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements-server.txt .
RUN /opt/venv/bin/pip install -r requirements-server.txt

FROM python:3.11-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/chesslens.db
RUN useradd --system --uid 10001 --create-home app && mkdir /data && chown app /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY server ./server
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"
# Behind nginx: trust X-Forwarded-For so rate limiting sees real client IPs.
CMD ["uvicorn", "server.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
