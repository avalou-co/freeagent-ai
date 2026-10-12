FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY pyproject.toml README.md ./
COPY freeagent_ai/ ./freeagent_ai/
RUN pip install --no-cache-dir '.[hosted]' && useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8080
CMD ["freeagent-ai", "serve"]
