import argparse

from config import settings as default_settings, database
from bithumb.client import BithumbClient
from db.store import Store
from engine.backtest import Backtest, BacktestResult


def run_backtest(client, store, settings) -> BacktestResult:
    symbols = client.get_top_symbols(settings.top_n, settings.min_trade_value_krw)
    candles = {}
    for symbol in symbols:
        try:
            df = client.get_daily_candles(symbol)
            if len(df) >= settings.long_period + 1:
                candles[symbol] = df
        except Exception as e:
            print(f"skip {symbol}: {e}")
    return Backtest(settings, store).run(candles)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="backtest", choices=["backtest"])
    args = parser.parse_args()

    store = Store(url=database.url())
    store.create_all()

    if args.mode == "backtest":
        result = run_backtest(BithumbClient(), store, default_settings)
        print(f"최종 자본: {result.final_capital:,.0f} KRW")
        print(f"수익률: {result.return_pct:.2f}%")
        print(f"거래 수: {result.num_trades}")


if __name__ == "__main__":
    main()
