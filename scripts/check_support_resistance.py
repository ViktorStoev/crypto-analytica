import json
import sys

from app.analytics.support_resistance import analyze_support_resistance
from app.analytics.support_resistance import load_recent_candles


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/check_support_resistance.py BTCUSDT 60")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]

    candles = load_recent_candles(symbol=symbol, interval=interval, limit=240)

    if not candles:
        print(
            json.dumps(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "error": "No candles found.",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    current_price = candles[-1]["close"]

    result = {
        "symbol": symbol,
        "interval": interval,
        "current_price": current_price,
        **analyze_support_resistance(
            symbol=symbol,
            interval=interval,
            current_price=current_price,
            limit=240,
        ),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
