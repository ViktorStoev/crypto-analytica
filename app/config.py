"""
Конфигурация проекта.

Этот файл отвечает за чтение настроек из переменных окружения и .env-файла.

Здесь собираются основные параметры:
- адрес Bybit API;
- настройки подключения к PostgreSQL/TimescaleDB;
- имя базы данных;
- пользователь БД;
- пароль БД.

Файл используется другими модулями проекта, например:
- app/db.py берет отсюда параметры подключения к БД;
- app/bybit_client.py берет отсюда BYBIT_BASE_URL.

Запускать этот файл отдельно не нужно.

Важно:
- секреты и пароли не должны храниться прямо в коде;
- они должны лежать в .env;
- .env должен быть добавлен в .gitignore.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


BYBIT_BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

DB_NAME = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB")
DB_USER = os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")


if not DB_NAME:
    raise RuntimeError("DB_NAME or POSTGRES_DB is not set")

if not DB_USER:
    raise RuntimeError("DB_USER or POSTGRES_USER is not set")

if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD or POSTGRES_PASSWORD is not set")