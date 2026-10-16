#!/bin/bash
# Installs Docker and runs Neo4j. Password is read from instance metadata.
set -euo pipefail
if ! command -v docker >/dev/null; then
  apt-get update -y && apt-get install -y docker.io
  systemctl enable --now docker
fi
PW=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/neo4j-password")
mkdir -p /opt/neo4j/data
docker rm -f trustbank-neo4j 2>/dev/null || true
docker run -d --name trustbank-neo4j --restart unless-stopped \
  -p 7687:7687 -p 7474:7474 \
  -v /opt/neo4j/data:/data \
  -e NEO4J_AUTH="neo4j/${PW}" \
  -e NEO4J_server_memory_heap_initial__size=512m \
  -e NEO4J_server_memory_heap_max__size=1g \
  -e NEO4J_server_memory_pagecache_size=512m \
  neo4j:5.26-community
