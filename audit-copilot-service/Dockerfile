FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY audit_copilot ./audit_copilot
COPY corpus ./corpus
COPY evals ./evals
COPY --from=ui /ui/dist ./ui/dist
RUN pip install --no-cache-dir --no-deps . && useradd -m -u 10001 copilot && mkdir /state && chown copilot:copilot /state
USER copilot
ENV COPILOT_STATE_PATH=/state/copilot.db
EXPOSE 8000
CMD ["uvicorn", "audit_copilot.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
