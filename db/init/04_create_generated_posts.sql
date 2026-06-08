-- История сформированных и опубликованных Telegram-постов.
--
-- Это обычная PostgreSQL-таблица, а не TimescaleDB hypertable.
-- Количество публикаций невелико, а главное требование здесь —
-- уникальность и надёжная фиксация статуса отправки.

CREATE TABLE IF NOT EXISTS generated_posts (
    id bigserial PRIMARY KEY,

    post_type text NOT NULL DEFAULT 'market_analysis',

    exchange text NOT NULL DEFAULT 'bybit',
    category text NOT NULL DEFAULT 'linear',

    symbol text NOT NULL,
    interval text NOT NULL,
    candle_time timestamptz NOT NULL,

    telegram_chat_id text NOT NULL,

    content text NOT NULL,
    content_hash char(64) NOT NULL,

    status text NOT NULL DEFAULT 'pending',

    disable_notification boolean NOT NULL DEFAULT true,

    telegram_message_id bigint,

    error_text text,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,

    CONSTRAINT chk_generated_posts_status
        CHECK (
            status IN (
                'pending',
                'sent',
                'failed',
                'unknown'
            )
        ),

    CONSTRAINT uq_generated_posts_publication
        UNIQUE (
            telegram_chat_id,
            post_type,
            exchange,
            category,
            symbol,
            interval,
            candle_time
        )
);


CREATE INDEX IF NOT EXISTS idx_generated_posts_status_created
    ON generated_posts (
        status,
        created_at DESC
    );


CREATE INDEX IF NOT EXISTS idx_generated_posts_symbol_time
    ON generated_posts (
        symbol,
        interval,
        candle_time DESC
    );