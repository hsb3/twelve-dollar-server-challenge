# Builds the seed database and runs test/test.sh: node, sqlite3, curl, jq, openssl.
FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 curl jq openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
