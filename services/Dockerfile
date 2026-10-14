FROM node:22-slim
WORKDIR /app

COPY agents/package*.json agents/
COPY fraud-api/package*.json fraud-api/
RUN cd agents && npm ci && cd ../fraud-api && npm ci

COPY agents/ agents/
COPY fraud-api/ fraud-api/

ENV NODE_ENV=production
WORKDIR /app/fraud-api
# Cloud Run sets PORT; server.ts reads it.
CMD ["npx", "tsx", "src/server.ts"]
