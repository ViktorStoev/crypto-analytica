"""Сервис надёжной публикации Telegram-постов.

Модуль отвечает за:

- резервирование публикации в PostgreSQL;
- защиту от повторной отправки;
- отправку сообщения через TelegramPublisher;
- сохранение статуса публикации;
- сохранение telegram_message_id;
- регистрацию ранее опубликованного сообщения.

Модуль не формирует рыночную аналитику и не создаёт текст поста.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import Engine, text

from app.telegram.publisher import (
    TelegramError,
    TelegramPublisher,
    TelegramTimeoutError,
)


POST_TYPE_MARKET_ANALYSIS = "market_analysis"


@dataclass(frozen=True)
class PublicationResult:
    """Результат попытки публикации."""

    publication_id: int
    status: str
    duplicate: bool
    telegram_message_id: int | None = None
    error_text: str | None = None

class PublicationResolutionError(RuntimeError):
    """Ошибка ручного разрешения проблемной публикации."""


def _normalize_candle_time(
    value: str | datetime,
) -> datetime:
    """Преобразовать время свечи в timezone-aware datetime."""

    if isinstance(value, datetime):
        result = value
    else:
        normalized = str(value).replace("Z", "+00:00")
        result = datetime.fromisoformat(normalized)

    if result.tzinfo is None:
        raise ValueError(
            "candle_time must contain timezone information."
        )

    return result


def _content_hash(content: str) -> str:
    """Рассчитать SHA-256 для текста поста."""

    return sha256(
        content.encode("utf-8")
    ).hexdigest()


def _get_existing_publication(
    connection: Any,
    *,
    telegram_chat_id: str,
    post_type: str,
    exchange: str,
    category: str,
    symbol: str,
    interval: str,
    candle_time: datetime,
) -> dict[str, Any] | None:
    """Найти публикацию по её уникальному ключу."""

    query = text(
        """
        SELECT
            id,
            status,
            telegram_message_id,
            error_text
        FROM generated_posts
        WHERE telegram_chat_id = :telegram_chat_id
          AND post_type = :post_type
          AND exchange = :exchange
          AND category = :category
          AND symbol = :symbol
          AND interval = :interval
          AND candle_time = :candle_time
        LIMIT 1
        """
    )

    row = connection.execute(
        query,
        {
            "telegram_chat_id": telegram_chat_id,
            "post_type": post_type,
            "exchange": exchange,
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "candle_time": candle_time,
        },
    ).mappings().first()

    if row is None:
        return None

    return dict(row)


def _reserve_publication(
    engine: Engine,
    *,
    telegram_chat_id: str,
    post_type: str,
    exchange: str,
    category: str,
    symbol: str,
    interval: str,
    candle_time: datetime,
    content: str,
    disable_notification: bool,
) -> PublicationResult:
    """Атомарно зарезервировать публикацию перед отправкой."""

    insert_query = text(
        """
        INSERT INTO generated_posts (
            post_type,
            exchange,
            category,
            symbol,
            interval,
            candle_time,
            telegram_chat_id,
            content,
            content_hash,
            status,
            disable_notification,
            last_attempt_at
        )
        VALUES (
            :post_type,
            :exchange,
            :category,
            :symbol,
            :interval,
            :candle_time,
            :telegram_chat_id,
            :content,
            :content_hash,
            'pending',
            :disable_notification,
            now()
        )
        ON CONFLICT (
            telegram_chat_id,
            post_type,
            exchange,
            category,
            symbol,
            interval,
            candle_time
        )
        DO NOTHING
        RETURNING
            id,
            status,
            telegram_message_id
        """
    )

    parameters = {
        "post_type": post_type,
        "exchange": exchange,
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "candle_time": candle_time,
        "telegram_chat_id": telegram_chat_id,
        "content": content,
        "content_hash": _content_hash(content),
        "disable_notification": disable_notification,
    }

    with engine.begin() as connection:
        inserted = connection.execute(
            insert_query,
            parameters,
        ).mappings().first()

        if inserted is not None:
            return PublicationResult(
                publication_id=int(inserted["id"]),
                status=str(inserted["status"]),
                duplicate=False,
                telegram_message_id=inserted[
                    "telegram_message_id"
                ],
            )

        existing = _get_existing_publication(
            connection,
            telegram_chat_id=telegram_chat_id,
            post_type=post_type,
            exchange=exchange,
            category=category,
            symbol=symbol,
            interval=interval,
            candle_time=candle_time,
        )

        if existing is None:
            raise RuntimeError(
                "Publication conflict occurred, "
                "but the existing row could not be found."
            )

        return PublicationResult(
            publication_id=int(existing["id"]),
            status=str(existing["status"]),
            duplicate=True,
            telegram_message_id=existing[
                "telegram_message_id"
            ],
            error_text=existing["error_text"],
        )


def _update_publication_status(
    engine: Engine,
    *,
    publication_id: int,
    status: str,
    telegram_message_id: int | None = None,
    error_text: str | None = None,
) -> None:
    """Обновить результат отправки в PostgreSQL."""

    query = text(
        """
        UPDATE generated_posts
        SET
            status = :status,
            telegram_message_id = :telegram_message_id,
            error_text = :error_text,
            sent_at = CASE
                WHEN :status = 'sent' THEN now()
                ELSE sent_at
            END,
            updated_at = now()
        WHERE id = :publication_id
        """
    )

    safe_error_text = (
        error_text[:2000]
        if error_text
        else None
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "publication_id": publication_id,
                "status": status,
                "telegram_message_id": telegram_message_id,
                "error_text": safe_error_text,
            },
        )


def publish_telegram_post(
    engine: Engine,
    publisher: TelegramPublisher,
    *,
    symbol: str,
    interval: str,
    candle_time: str | datetime,
    content: str,
    disable_notification: bool = True,
    post_type: str = POST_TYPE_MARKET_ANALYSIS,
    exchange: str = "bybit",
    category: str = "linear",
) -> PublicationResult:
    """Опубликовать пост с защитой от повторной отправки."""

    normalized_candle_time = _normalize_candle_time(
        candle_time
    )

    reservation = _reserve_publication(
        engine,
        telegram_chat_id=publisher.chat_id,
        post_type=post_type,
        exchange=exchange,
        category=category,
        symbol=symbol,
        interval=interval,
        candle_time=normalized_candle_time,
        content=content,
        disable_notification=disable_notification,
    )

    if reservation.duplicate:
        return reservation

    try:
        telegram_result = publisher.send_message(
            text=content,
            disable_notification=disable_notification,
        )

    except TelegramTimeoutError as exc:
        _update_publication_status(
            engine,
            publication_id=reservation.publication_id,
            status="unknown",
            error_text=str(exc),
        )

        return PublicationResult(
            publication_id=reservation.publication_id,
            status="unknown",
            duplicate=False,
            error_text=str(exc),
        )

    except TelegramError as exc:
        _update_publication_status(
            engine,
            publication_id=reservation.publication_id,
            status="failed",
            error_text=str(exc),
        )

        return PublicationResult(
            publication_id=reservation.publication_id,
            status="failed",
            duplicate=False,
            error_text=str(exc),
        )

    telegram_message_id = telegram_result.get(
        "message_id"
    )

    if not isinstance(telegram_message_id, int):
        error_text = (
            "Telegram returned a successful response "
            "without a valid message_id."
        )

        _update_publication_status(
            engine,
            publication_id=reservation.publication_id,
            status="unknown",
            error_text=error_text,
        )

        return PublicationResult(
            publication_id=reservation.publication_id,
            status="unknown",
            duplicate=False,
            error_text=error_text,
        )

    _update_publication_status(
        engine,
        publication_id=reservation.publication_id,
        status="sent",
        telegram_message_id=telegram_message_id,
    )

    return PublicationResult(
        publication_id=reservation.publication_id,
        status="sent",
        duplicate=False,
        telegram_message_id=telegram_message_id,
    )


def register_existing_publication(
    engine: Engine,
    publisher: TelegramPublisher,
    *,
    symbol: str,
    interval: str,
    candle_time: str | datetime,
    content: str,
    telegram_message_id: int,
    disable_notification: bool = True,
    post_type: str = POST_TYPE_MARKET_ANALYSIS,
    exchange: str = "bybit",
    category: str = "linear",
) -> PublicationResult:
    """Зарегистрировать уже опубликованный Telegram-пост."""

    normalized_candle_time = _normalize_candle_time(
        candle_time
    )

    query = text(
        """
        INSERT INTO generated_posts (
            post_type,
            exchange,
            category,
            symbol,
            interval,
            candle_time,
            telegram_chat_id,
            content,
            content_hash,
            status,
            disable_notification,
            telegram_message_id,
            sent_at
        )
        VALUES (
            :post_type,
            :exchange,
            :category,
            :symbol,
            :interval,
            :candle_time,
            :telegram_chat_id,
            :content,
            :content_hash,
            'sent',
            :disable_notification,
            :telegram_message_id,
            now()
        )
        ON CONFLICT (
            telegram_chat_id,
            post_type,
            exchange,
            category,
            symbol,
            interval,
            candle_time
        )
        DO NOTHING
        RETURNING
            id,
            status,
            telegram_message_id
        """
    )

    parameters = {
        "post_type": post_type,
        "exchange": exchange,
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "candle_time": normalized_candle_time,
        "telegram_chat_id": publisher.chat_id,
        "content": content,
        "content_hash": _content_hash(content),
        "disable_notification": disable_notification,
        "telegram_message_id": telegram_message_id,
    }

    with engine.begin() as connection:
        inserted = connection.execute(
            query,
            parameters,
        ).mappings().first()

        if inserted is not None:
            return PublicationResult(
                publication_id=int(inserted["id"]),
                status=str(inserted["status"]),
                duplicate=False,
                telegram_message_id=inserted[
                    "telegram_message_id"
                ],
            )

        existing = _get_existing_publication(
            connection,
            telegram_chat_id=publisher.chat_id,
            post_type=post_type,
            exchange=exchange,
            category=category,
            symbol=symbol,
            interval=interval,
            candle_time=normalized_candle_time,
        )

        if existing is None:
            raise RuntimeError(
                "Existing publication could not be found."
            )

        return PublicationResult(
            publication_id=int(existing["id"]),
            status=str(existing["status"]),
            duplicate=True,
            telegram_message_id=existing[
                "telegram_message_id"
            ],
            error_text=existing["error_text"],
        )
def get_publication_by_id(
    engine: Engine,
    publication_id: int,
) -> dict[str, Any]:
    """Получить публикацию по её внутреннему ID."""

    query = text(
        """
        SELECT
            id,
            post_type,
            exchange,
            category,
            symbol,
            interval,
            candle_time,
            telegram_chat_id,
            content,
            content_hash,
            status,
            disable_notification,
            telegram_message_id,
            error_text,
            retry_count,
            last_attempt_at,
            manual_reviewed_at,
            manual_review_note,
            created_at,
            updated_at,
            sent_at
        FROM generated_posts
        WHERE id = :publication_id
        """
    )

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {
                "publication_id": publication_id,
            },
        ).mappings().first()

    if row is None:
        raise PublicationResolutionError(
            f"Publication id={publication_id} was not found."
        )

    return dict(row)


def mark_unknown_publication_as_sent(
    engine: Engine,
    *,
    publication_id: int,
    telegram_message_id: int,
    review_note: str,
) -> PublicationResult:
    """Подтвердить, что unknown-публикация реально появилась в Telegram."""

    if telegram_message_id <= 0:
        raise PublicationResolutionError(
            "telegram_message_id must be greater than zero."
        )

    normalized_note = review_note.strip()

    if not normalized_note:
        raise PublicationResolutionError(
            "A manual review note is required."
        )

    query = text(
        """
        UPDATE generated_posts
        SET
            status = 'sent',
            telegram_message_id = :telegram_message_id,
            error_text = NULL,
            sent_at = COALESCE(sent_at, now()),
            manual_reviewed_at = now(),
            manual_review_note = :review_note,
            updated_at = now()
        WHERE id = :publication_id
          AND status = 'unknown'
        RETURNING
            id,
            status,
            telegram_message_id,
            error_text
        """
    )

    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "publication_id": publication_id,
                "telegram_message_id": telegram_message_id,
                "review_note": normalized_note[:2000],
            },
        ).mappings().first()

        if row is None:
            existing = connection.execute(
                text(
                    """
                    SELECT id, status, telegram_message_id
                    FROM generated_posts
                    WHERE id = :publication_id
                    """
                ),
                {
                    "publication_id": publication_id,
                },
            ).mappings().first()

            if existing is None:
                raise PublicationResolutionError(
                    f"Publication id={publication_id} was not found."
                )

            raise PublicationResolutionError(
                "Publication cannot be marked as sent: "
                f"id={publication_id}, "
                f"current_status={existing['status']}, "
                f"current_message_id="
                f"{existing['telegram_message_id']}. "
                "Only status=unknown can be resolved this way."
            )

    return PublicationResult(
        publication_id=int(row["id"]),
        status=str(row["status"]),
        duplicate=False,
        telegram_message_id=row["telegram_message_id"],
        error_text=row["error_text"],
    )


def retry_unknown_publication(
    engine: Engine,
    publisher: TelegramPublisher,
    *,
    publication_id: int,
    review_note: str,
) -> PublicationResult:
    """Повторить unknown-публикацию после ручного подтверждения отсутствия поста."""

    normalized_note = review_note.strip()

    if not normalized_note:
        raise PublicationResolutionError(
            "A manual review note is required."
        )

    # Сначала атомарно блокируем строку и переводим unknown → pending.
    #
    # FOR UPDATE не позволяет двум операторам одновременно
    # разрешить повтор одной и той же публикации.
    with engine.begin() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    id,
                    status,
                    content,
                    disable_notification,
                    telegram_message_id
                FROM generated_posts
                WHERE id = :publication_id
                FOR UPDATE
                """
            ),
            {
                "publication_id": publication_id,
            },
        ).mappings().first()

        if row is None:
            raise PublicationResolutionError(
                f"Publication id={publication_id} was not found."
            )

        if row["status"] != "unknown":
            raise PublicationResolutionError(
                "Publication cannot be retried: "
                f"id={publication_id}, "
                f"current_status={row['status']}. "
                "Only status=unknown can be retried."
            )

        if row["telegram_message_id"] is not None:
            raise PublicationResolutionError(
                "Publication has telegram_message_id and cannot be retried."
            )

        connection.execute(
            text(
                """
                UPDATE generated_posts
                SET
                    status = 'pending',
                    error_text = NULL,
                    retry_count = retry_count + 1,
                    last_attempt_at = now(),
                    manual_reviewed_at = now(),
                    manual_review_note = :review_note,
                    updated_at = now()
                WHERE id = :publication_id
                """
            ),
            {
                "publication_id": publication_id,
                "review_note": normalized_note[:2000],
            },
        )

        content = str(row["content"])
        disable_notification = bool(
            row["disable_notification"]
        )

    # Сетевой запрос выполняем после завершения транзакции.
    # Не держим блокировку строки во время обращения к Telegram.
    try:
        telegram_result = publisher.send_message(
            text=content,
            disable_notification=disable_notification,
        )

    except TelegramTimeoutError as exc:
        _update_publication_status(
            engine,
            publication_id=publication_id,
            status="unknown",
            error_text=str(exc),
        )

        return PublicationResult(
            publication_id=publication_id,
            status="unknown",
            duplicate=False,
            error_text=str(exc),
        )

    except TelegramError as exc:
        _update_publication_status(
            engine,
            publication_id=publication_id,
            status="failed",
            error_text=str(exc),
        )

        return PublicationResult(
            publication_id=publication_id,
            status="failed",
            duplicate=False,
            error_text=str(exc),
        )

    telegram_message_id = telegram_result.get(
        "message_id"
    )

    if not isinstance(telegram_message_id, int):
        error_text = (
            "Telegram returned a successful response "
            "without a valid message_id."
        )

        _update_publication_status(
            engine,
            publication_id=publication_id,
            status="unknown",
            error_text=error_text,
        )

        return PublicationResult(
            publication_id=publication_id,
            status="unknown",
            duplicate=False,
            error_text=error_text,
        )

    _update_publication_status(
        engine,
        publication_id=publication_id,
        status="sent",
        telegram_message_id=telegram_message_id,
    )

    return PublicationResult(
        publication_id=publication_id,
        status="sent",
        duplicate=False,
        telegram_message_id=telegram_message_id,
    )