import argparse

from config import settings as default_settings, database
from bithumb.client import BithumbClient
from db.store import Store
from engine.backtest import Backtest, BacktestResult
from engine.paper import PaperTrader
from engine.tuner import run_grid


def fetch_candles(client, settings, min_len: int | None = None) -> dict:
    """상위 종목의 일봉 캔들을 수집한다. min_len 미만 종목은 제외."""
    if min_len is None:
        min_len = settings.long_period + 1
    symbols = client.get_top_symbols(settings.top_n, settings.min_trade_value_krw)
    candles = {}
    for symbol in symbols:
        try:
            df = client.get_daily_candles(symbol)
            if len(df) >= min_len:
                candles[symbol] = df
        except Exception as e:
            print(f"skip {symbol}: {e}")
    return candles


def run_backtest(client, store, settings) -> BacktestResult:
    candles = fetch_candles(client, settings)
    return Backtest(settings, store, fee_rate=settings.fee_rate).run(candles)


def run_paper(client, store, settings) -> dict:
    return PaperTrader(settings, store, client, fee_rate=settings.fee_rate).run_once()


# 튜닝 기본 그리드 (추세추종 파라미터 탐색)
DEFAULT_GRID = {
    "short_period": [10, 15, 20],
    "long_period": [40, 60],
    "trailing_stop_pct": [0.05, 0.10],
}


def run_tune(client, settings, grid: dict) -> list[dict]:
    # 그리드 내 최대 long_period 기준으로 캔들을 한 번만 수집해 전 조합 재사용
    max_long = max(grid.get("long_period", [settings.long_period]))
    candles = fetch_candles(client, settings, min_len=max_long + 1)
    print(f"수집된 종목 수: {len(candles)}, 조합 수: "
          f"{_grid_size(grid)} (캔들 재사용)")
    return run_grid(candles, settings, grid, fee_rate=settings.fee_rate)


def _grid_size(grid: dict) -> int:
    n = 1
    for v in grid.values():
        n *= len(v)
    return n


def _print_tune_table(rows: list[dict]) -> None:
    print("\n순위 | short/long | 트레일링 | 수익률 | MDD | 거래수")
    print("-" * 60)
    for i, r in enumerate(rows, 1):
        print(f"{i:>3} | {r['short_period']:>2}/{r['long_period']:<2} "
              f"| {r['trailing_stop_pct']*100:>4.0f}% "
              f"| {r['return_pct']:>8.1f}% | {r['mdd_pct']:>6.1f}% "
              f"| {r['num_trades']:>5}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="backtest",
                        choices=["backtest", "tune", "paper"])
    args = parser.parse_args()

    if args.mode == "backtest":
        store = Store(url=database.url())
        store.create_all()
        result = run_backtest(BithumbClient(), store, default_settings)
        print(f"최종 자본: {result.final_capital:,.0f} KRW")
        print(f"수익률: {result.return_pct:.2f}%")
        print(f"거래 수: {result.num_trades}")

    elif args.mode == "tune":
        rows = run_tune(BithumbClient(), default_settings, DEFAULT_GRID)
        _print_tune_table(rows)
        best = rows[0]
        print(f"\n최고 조합: short={best['short_period']} "
              f"long={best['long_period']} "
              f"트레일링={best['trailing_stop_pct']*100:.0f}% "
              f"→ 수익률 {best['return_pct']:.1f}%, MDD {best['mdd_pct']:.1f}%")

    elif args.mode == "paper":
        store = Store(url=database.url())
        store.create_all()
        summary = run_paper(BithumbClient(), store, default_settings)
        print(f"현금: {summary['cash']:,.0f} KRW")
        print(f"보유 종목: {summary['positions']}개")
        print(f"당일 체결: {summary['filled']}건")
        print(f"총자산: {summary['total']:,.0f} KRW")


if __name__ == "__main__":
    main()
