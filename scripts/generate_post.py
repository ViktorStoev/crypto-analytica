import sys

from sqlalchemy import create_engine

from app.analytics.data_loader import get_database_url
from app.analytics.market_analysis import build_analysis
from app.posting.template_generator import build_telegram_post


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/generate_post.py BTCUSDT 60")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]

    engine = create_engine(get_database_url())

    analysis = build_analysis(
        engine=engine,
        symbol=symbol,
        interval=interval,
    )

    if "error" in analysis:
        print(analysis["error"])
        sys.exit(1)

    post = build_telegram_post(analysis)

    print(post)


if __name__ == "__main__":
    main()
