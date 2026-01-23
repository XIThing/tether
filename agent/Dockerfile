# Build UI
FROM node:20-slim AS ui-builder
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# Build agent
FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY agent/pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy agent code
COPY agent/tether ./tether

# Copy built UI into static_ui
COPY --from=ui-builder /ui/dist ./tether/static_ui

# Create data directory
RUN mkdir -p /app/data

ENV AGENT_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8787

CMD ["python", "-m", "uvicorn", "tether.main:app", "--host", "0.0.0.0", "--port", "8787"]
