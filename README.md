# crypto-analytica

`crypto-analytica` is a local MVP project for collecting, storing and analyzing cryptocurrency market data from Bybit.

The project is focused on preparing structured market data for future automated analytics and Telegram content generation.

## Current status

The project currently supports:

* collecting market data from Bybit public API;
* storing data in TimescaleDB/PostgreSQL;
* running the application in Docker;
* initializing database schema with SQL scripts;
* collecting candles, tickers, funding rates and open interest;
* calculating technical indicators;
* running basic symbol analysis scripts.

## Tech stack

* Python
* Docker / Docker Compose
* PostgreSQL
* TimescaleDB
* pgAdmin
* Bybit public API
* pandas
* SQLAlchemy
* psycopg

## Project structure

```text
.
├── app
│   ├── bybit_client.py
│   ├── config.py
│   ├── db.py
│   └── __init__.py
├── db
│   └── init
│       ├── 01_extensions.sql
│       ├── 02_schema.sql
│       └── 03_create_indicators.sql
├── scripts
│   ├── analyze_symbol.py
│   ├── backfill_candles.py
│   ├── backfill_funding_rates.py
│   ├── backfill_open_interest.py
│   ├── calculate_indicators.py
│   ├── check_bybit_public.py
│   ├── collect_market_once.py
│   ├── collect_tickers_once.py
│   ├── insert_btc_1h_candles.py
│   ├── read_last_candles.py
│   └── sync_instruments.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── .gitignore
```

## Environment variables

Create a local `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Then edit `.env` and set real local values.

The `.env` file is intentionally ignored by Git and must not be committed.

## Start the project

Run the infrastructure and application containers:

```bash
docker compose up -d
```

Check that the containers are running:

```bash
docker compose ps
```

## Run scripts

Check public Bybit API availability:

```bash
docker compose run --rm app python scripts/check_bybit_public.py
```

Sync instruments:

```bash
docker compose run --rm app python scripts/sync_instruments.py
```

Collect market data once for BTCUSDT:

```bash
docker compose run --rm app python scripts/collect_market_once.py BTCUSDT
```

Calculate indicators:

```bash
docker compose run --rm app python scripts/calculate_indicators.py BTCUSDT
```

Analyze symbol:

```bash
docker compose run --rm app python scripts/analyze_symbol.py BTCUSDT
```

## Daily summary production enablement

`daily_summary` is disabled by default. Prepare BTC/ETH/SOL data before enabling it permanently.

Bootstrap candles, fresh market data and indicators:

```bash
docker compose run --rm app python scripts/bootstrap_daily_summary_symbols.py --symbols BTCUSDT ETHUSDT SOLUSDT --interval 60 --days 180
```

Preview the generated post:

```bash
docker compose run --rm app python scripts/generate_content_post.py --type daily_summary --symbols BTCUSDT ETHUSDT SOLUSDT --interval 60
```

Run the scheduler job once with daily summary enabled only for this command:

```bash
docker compose run --rm -e SCHEDULER_DAILY_SUMMARY_ENABLED=true scheduler python scripts/run_scheduler.py --run-once --job daily_summary
```

Enable it permanently in local `.env` after bootstrap succeeds:

```bash
SCHEDULER_DAILY_SUMMARY_ENABLED=true
```
## Notes

This project is currently an MVP and is intended for local development and experimentation.

Real credentials, database dumps, local market data exports and Docker volumes must not be committed to the repository.
