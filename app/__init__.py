"""
Пакет app.

Этот файл нужен, чтобы Python воспринимал папку app как пакет.

Благодаря этому другие файлы могут импортировать модули так:

    from app.bybit_client import BybitClient
    from app.db import get_connection
    from app.config import DB_HOST

Обычно этот файл может быть пустым.
Запускать его отдельно не нужно.
"""