"""
Подключение к PostgreSQL/TimescaleDB.

Этот файл содержит функцию get_connection(), которая создает подключение к базе данных.

Используется всеми скриптами, которым нужно читать или записывать данные:

Запускать этот файл отдельно не нужно.

Пример использования в коде:

    from app.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
"""

import psycopg

from app.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def get_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )