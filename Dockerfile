FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[service]"
ENV NIYAM_DB=/data/niyam.db NIYAM_POLICIES=/app/config/policies.yaml
VOLUME /data
EXPOSE 8470
CMD ["uvicorn", "niyam.service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8470"]
