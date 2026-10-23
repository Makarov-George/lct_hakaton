# Образ PostgreSQL со схемой
FROM postgres:16-alpine

LABEL org.opencontainers.image.title="cm-db" \
      org.opencontainers.image.description="PostgreSQL 16 with construction monitoring schema and reference data"

ENV POSTGRES_DB=construction_monitoring \
    POSTGRES_USER=cm_admin \
    TZ=Europe/Moscow

# Миграции:
COPY migrations/*.sql /docker-entrypoint-initdb.d/

HEALTHCHECK --interval=3s --timeout=3s --start-period=60s --retries=20 \
    CMD pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" || exit 1
