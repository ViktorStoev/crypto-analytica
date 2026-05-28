-- Инициализация расширений PostgreSQL.
--
-- Этот файл выполняется автоматически при первом создании контейнера PostgreSQL/TimescaleDB.
--
-- Здесь включается расширение TimescaleDB.
-- Оно нужно, чтобы PostgreSQL умел эффективно работать с временными рядами:
-- свечами, tickers, funding rate, open interest и другими рыночными данными.
--
-- Запускать этот файл вручную обычно не нужно.
-- Docker выполняет его автоматически при первом создании базы,
-- потому что папка db/init подключена в docker-compose.yml как:
--
--     /docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS timescaledb;