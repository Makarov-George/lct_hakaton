#!/bin/sh
set -eu
DIR=$(cd "$(dirname "$0")" && pwd)

if [ "${1:-}" = "reset" ]; then
  docker compose -f "$DIR/docker-compose.yml" down -v
fi

docker compose -f "$DIR/docker-compose.yml" up -d --build
