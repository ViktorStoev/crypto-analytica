-- Основная схема базы данных проекта.
--
-- Этот файл создает таблицы для хранения рыночных данных из Bybit.
--
-- Основные таблицы:
--
-- instruments:
--     справочник торговых инструментов Bybit.
--     Например: BTCUSDT, ETHUSDT, SOLUSDT.
--
-- candles:
--     свечи OHLCV.
--     Здесь хранятся open, high, low, close, volume и turnover.
--
-- tickers:
--     текущие рыночные снимки.
--     Здесь хранятся last_price, mark_price, index_price,
--     volume_24h, funding_rate, open_interest и другие поля.
--
-- funding_rates:
--     история funding rate по фьючерсным контрактам.
--
-- open_interest:
--     история open interest по фьючерсным контрактам.
--
-- Таблицы candles, tickers, funding_rates и open_interest
-- создаются как hypertables TimescaleDB, потому что это временные ряды.
--
-- Запускать этот файл вручную обычно не нужно.
-- Docker выполняет его автоматически при первом создании базы.

CREATE TABLE IF NOT EXISTS instruments (
    exchange        text        NOT NULL DEFAULT 'bybit',
    category        text        NOT NULL,
    symbol          text        NOT NULL,

    base_coin       text,
    quote_coin      text,
    settle_coin     text,
    contract_type   text,
    status          text,

    price_scale     integer,
    tick_size       numeric,
    qty_step        numeric,
    min_order_qty   numeric,
    max_order_qty   numeric,

    launch_time_ms  bigint,
    delivery_time_ms bigint,

    raw             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    updated_at      timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (exchange, category, symbol)
);


CREATE TABLE IF NOT EXISTS candles (
    exchange        text        NOT NULL DEFAULT 'bybit',
    category        text        NOT NULL,
    symbol          text        NOT NULL,
    interval        text        NOT NULL,

    open_time       timestamptz NOT NULL,
    open_price      numeric     NOT NULL,
    high_price      numeric     NOT NULL,
    low_price       numeric     NOT NULL,
    close_price     numeric     NOT NULL,
    volume          numeric     NOT NULL,
    turnover        numeric,

    ingested_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (exchange, category, symbol, interval, open_time)
);

SELECT create_hypertable(
    'candles',
    by_range('open_time'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval_time_desc
    ON candles (exchange, category, symbol, interval, open_time DESC);


CREATE TABLE IF NOT EXISTS tickers (
    exchange        text        NOT NULL DEFAULT 'bybit',
    category        text        NOT NULL,
    symbol          text        NOT NULL,

    ts              timestamptz NOT NULL,

    last_price      numeric,
    mark_price      numeric,
    index_price     numeric,

    high_price_24h  numeric,
    low_price_24h   numeric,
    prev_price_24h  numeric,
    price_24h_pcnt  numeric,

    volume_24h      numeric,
    turnover_24h    numeric,

    funding_rate    numeric,
    open_interest   numeric,

    raw             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ingested_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (exchange, category, symbol, ts)
);

SELECT create_hypertable(
    'tickers',
    by_range('ts'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_tickers_symbol_time_desc
    ON tickers (exchange, category, symbol, ts DESC);


CREATE TABLE IF NOT EXISTS funding_rates (
    exchange        text        NOT NULL DEFAULT 'bybit',
    category        text        NOT NULL,
    symbol          text        NOT NULL,

    funding_time    timestamptz NOT NULL,
    funding_rate    numeric     NOT NULL,

    raw             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ingested_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (exchange, category, symbol, funding_time)
);

SELECT create_hypertable(
    'funding_rates',
    by_range('funding_time'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_funding_symbol_time_desc
    ON funding_rates (exchange, category, symbol, funding_time DESC);


CREATE TABLE IF NOT EXISTS open_interest (
    exchange        text        NOT NULL DEFAULT 'bybit',
    category        text        NOT NULL,
    symbol          text        NOT NULL,
    interval        text        NOT NULL,

    ts              timestamptz NOT NULL,
    open_interest   numeric     NOT NULL,

    raw             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ingested_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (exchange, category, symbol, interval, ts)
);

SELECT create_hypertable(
    'open_interest',
    by_range('ts'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_open_interest_symbol_time_desc
    ON open_interest (exchange, category, symbol, interval, ts DESC);