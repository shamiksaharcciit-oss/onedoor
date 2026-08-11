FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[service]"
ENV ONEDOOR_DB=/data/onedoor.db ONEDOOR_POLICIES=/app/config/policies.yaml
VOLUME /data
EXPOSE 8470
CMD ["uvicorn", "onedoor.service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8470"]
