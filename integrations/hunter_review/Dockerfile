# Use the existing local runtime image; no package download is needed.
ARG BASE_IMAGE=animus-kernel:ci-repair
FROM ${BASE_IMAGE}
USER root
WORKDIR /app
# Package only the real Hunter domain models/auditor, excluding personal-memory boot.
COPY packages/core/animus/hunter_os/models.py packages/core/animus/hunter_os/audit.py /app/vendor/animus/hunter_os/
RUN touch /app/vendor/animus/__init__.py /app/vendor/animus/hunter_os/__init__.py
COPY integrations/hunter_review/__init__.py integrations/hunter_review/review.py integrations/hunter_review/server.py /app/integrations/hunter_review/
ENV PYTHONPATH=/app/vendor:/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN python -c "import yaml; from animus.hunter_os.audit import audit_record"
USER 65532:65532
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/healthz', timeout=3)"
ENTRYPOINT ["python", "-m", "integrations.hunter_review.server"]
CMD ["--host", "0.0.0.0", "--sources", "/sources", "--state", "/state", "--token-file", "/config/connector.token"]
