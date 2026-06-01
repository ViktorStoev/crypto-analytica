import json
import sys

from sqlalchemy import create_engine

from app.analytics.market_analysis import build_analysis
from app.analytics.market_analysis import get_database_url


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/analyze_symbol.py BTCUSDT 60")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]

    engine = create_engine(get_database_url())

    analysis = build_analysis(
        engine=engine,
        symbol=symbol,
        interval=interval,
    )

    print(json.dumps(analysis, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
