CREATE TABLE IF NOT EXISTS indicators (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time TIMESTAMPTZ NOT NULL,

    ema_20 DOUBLE PRECISION,
    ema_50 DOUBLE PRECISION,
    ema_200 DOUBLE PRECISION,

    rsi_14 DOUBLE PRECISION,

    macd_line DOUBLE PRECISION,
    macd_signal DOUBLE PRECISION,
    macd_hist DOUBLE PRECISION,

    atr_14 DOUBLE PRECISION,

    volume_sma_20 DOUBLE PRECISION,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (symbol, interval, open_time)
);

SELECT create_hypertable('indicators', 'open_time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_indicators_symbol_interval_time_desc
ON indicators (symbol, interval, open_time DESC);