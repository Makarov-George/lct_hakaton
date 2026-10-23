import os
import psycopg
from psycopg.rows import dict_row
from contextlib import contextmanager

DATABASE_URL = os.environ["CM_DATABASE_URL"]


@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()


def fetch_one(query, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchone()


def execute(query, params=None):
    """INSERT/UPDATE/DELETE. Возвращает первую строку, если есть RETURNING."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            try:
                row = cur.fetchone()
            except psycopg.ProgrammingError:
                row = None
            conn.commit()
            return row


def execute_many(query, seq_of_params):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, seq_of_params)
            conn.commit()


def list_tables():
    return fetch_all("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)