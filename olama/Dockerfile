FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY . .
RUN uv sync --frozen
CMD ["uv", "run", "llm.py"]
