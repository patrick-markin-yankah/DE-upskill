"""Write one date of FinCore raw files to MinIO. Same date and counts => same files.

Usage:
  python generate_sources.py YYYY-MM-DD
  python generate_sources.py YYYY-MM-DD --trades N --market-rows N --positions N
  python generate_sources.py YYYY-MM-DD --dirty

Counts default to a small day (1000 trades, 50 equity prices, 80 positions).
Pass the brief's sizes when you want that day: --trades 500000 --market-rows 50000 --positions 8000.
"""
import argparse
import csv
import io
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

BUCKET = "fincore-raw"
GBPUSD = Decimal("1.271350")
UNPRICED_SYMBOL = "NOCLOSE"
HAPPY_BAD_PCT = 1
DIRTY_BAD_PCT = 5
HAPPY_UNPRICED = 12
DIRTY_UNPRICED = 120
POSITIONS_PER_PORTFOLIO = 20


@dataclass
class Equity:
    symbol: str
    currency: str
    close: Decimal | None
    status: str  # ok, blank, non_positive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one FinCore raw day in MinIO")
    parser.add_argument("trade_date", help="YYYY-MM-DD")
    parser.add_argument("--trades", type=int, default=1000, help="FIX lines to write (default 1000)")
    parser.add_argument(
        "--market-rows",
        type=int,
        default=50,
        help="Equity price rows. fx.csv is extra and holds GBP (default 50)",
    )
    parser.add_argument(
        "--positions",
        type=int,
        default=80,
        help="Portfolio positions across all accounts (default 80)",
    )
    parser.add_argument(
        "--dirty",
        action="store_true",
        help="Push the reject rate over 2%% and plant 100+ unpriced trades",
    )
    args = parser.parse_args()
    try:
        datetime.strptime(args.trade_date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit("trade_date must be YYYY-MM-DD")
    if args.trades < 1:
        raise SystemExit("--trades must be at least 1")
    if args.market_rows < 2:
        raise SystemExit("--market-rows must be at least 2 (AAPL and VOD)")
    if args.positions < 2:
        raise SystemExit("--positions must be at least 2 (one AAPL, one VOD)")
    return args


def money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def random_price() -> Decimal:
    cents = random.randint(500, 50000)
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def build_equities(n: int) -> list[Equity]:
    """AAPL and VOD first. Spare rows at the end carry blank or non-positive closes."""
    rows = [
        Equity("AAPL", "USD", Decimal("155.00"), "ok"),
        Equity("VOD", "GBP", Decimal("72.50"), "ok"),
    ]
    for i in range(2, n):
        rows.append(Equity(f"S{i:05d}", "USD", random_price(), "ok"))

    spare = list(range(2, n))
    tail = list(reversed(spare))
    n_nonpositive = 1 if len(tail) >= 1 else 0
    n_blank = min(3, len(tail) - n_nonpositive)
    for offset in range(n_nonpositive):
        rows[tail[offset]].close = Decimal("0.00")
        rows[tail[offset]].status = "non_positive"
    for offset in range(n_blank):
        rows[tail[n_nonpositive + offset]].close = None
        rows[tail[n_nonpositive + offset]].status = "blank"
    return rows


def fix_line(
    order_id: str,
    portfolio_id: str,
    symbol: str,
    side: str,
    qty: int,
    price: Decimal,
    currency: str,
    transact_time: str,
) -> str:
    return "|".join(
        [
            "8=FIX.4.4",
            "9=0",
            "35=8",
            f"37={order_id}",
            f"1={portfolio_id}",
            f"55={symbol}",
            f"54={side}",
            f"38={qty}",
            f"6={money(price)}",
            f"15={currency}",
            f"60={transact_time}",
            "10=000",
        ]
    )


def drop_tag(line: str, tag: str) -> str:
    prefix = f"{tag}="
    return "|".join(part for part in line.split("|") if not part.startswith(prefix))


def transact_time(trade_date: str) -> str:
    ymd = trade_date.replace("-", "")
    hh = random.randint(9, 16)
    mm = random.randint(0, 59)
    ss = random.randint(0, 59)
    return f"{ymd}-{hh:02d}:{mm:02d}:{ss:02d}"


def build_trades(
    trade_date: str,
    n: int,
    portfolio_ids: list[str],
    tradable: list[Equity],
    n_bad: int,
    n_unpriced: int,
) -> list[str]:
    roles = (["bad"] * n_bad) + (["unpriced"] * n_unpriced) + (["ok"] * (n - n_bad - n_unpriced))
    random.shuffle(roles)
    lower_left = 4
    lines = []
    ymd = trade_date.replace("-", "")
    for i, role in enumerate(roles):
        order_id = f"ORD-{ymd}-{i:07d}"
        portfolio_id = random.choice(portfolio_ids)
        when = transact_time(trade_date)
        if role == "bad":
            kind = i % 3
            if kind == 0:
                lines.append("8=FIX.4.4|35=8|BROKEN")
            else:
                equity = tradable[i % len(tradable)]
                line = fix_line(
                    order_id,
                    portfolio_id,
                    equity.symbol,
                    random.choice(("1", "2")),
                    random.randint(1, 400),
                    random_price(),
                    equity.currency,
                    when,
                )
                lines.append(drop_tag(line, "37" if kind == 1 else "55"))
            continue
        if role == "unpriced":
            symbol, currency = UNPRICED_SYMBOL, "USD"
        else:
            equity = tradable[i % len(tradable)]
            symbol, currency = equity.symbol, equity.currency
            if symbol == "AAPL" and lower_left and random.random() < 0.5:
                symbol = "aapl"
                lower_left -= 1
        lines.append(
            fix_line(
                order_id,
                portfolio_id,
                symbol,
                random.choice(("1", "2")),
                random.randint(1, 400),
                random_price(),
                currency,
                when,
            )
        )
    return lines


def build_portfolios(trade_date: str, n_positions: int, equities: list[Equity]) -> list[dict]:
    tradable = [row for row in equities if row.status == "ok" and row.symbol != "AAPL"]
    blank = next((row for row in equities if row.status == "blank"), None)
    positions: list[dict] = [
        {"symbol": "aapl", "quantity": random.randint(1, 400), "currency": "USD"},
        {"symbol": "VOD", "quantity": random.randint(1, 400), "currency": "GBP"},
    ]
    if n_positions >= 6:
        positions.append(
            {"symbol": UNPRICED_SYMBOL, "quantity": random.randint(1, 50), "currency": "USD"}
        )
    if blank is not None and n_positions >= 8:
        positions.append(
            {"symbol": blank.symbol, "quantity": random.randint(1, 50), "currency": blank.currency}
        )
    while len(positions) < n_positions:
        equity = random.choice(tradable)
        positions.append(
            {
                "symbol": equity.symbol,
                "quantity": random.randint(1, 400),
                "currency": equity.currency,
            }
        )
    positions = positions[:n_positions]

    portfolios = []
    for offset in range(0, len(positions), POSITIONS_PER_PORTFOLIO):
        chunk = positions[offset : offset + POSITIONS_PER_PORTFOLIO]
        n = (offset // POSITIONS_PER_PORTFOLIO) + 1
        portfolios.append(
            {
                "portfolio_id": f"P-{n}",
                "as_of": trade_date,
                "positions": chunk,
                "metadata": {
                    "risk_limits": {
                        "max_gross_exposure_usd": 1_000_000 + (n * 250_000),
                        "max_position_pct": 0.10,
                    }
                },
            }
        )
    return portfolios


def equities_csv(rows: list[Equity], trade_date: str) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["symbol", "asset_class", "close_price", "currency", "price_date"])
    for row in rows:
        close = "" if row.close is None else money(row.close)
        writer.writerow([row.symbol, "equity", close, row.currency, trade_date])
    return buf.getvalue()


def fx_csv(trade_date: str) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["symbol", "asset_class", "close_price", "currency", "price_date"])
    writer.writerow(["GBP", "fx", f"{GBPUSD.quantize(Decimal('0.000001'))}", "USD", trade_date])
    return buf.getvalue()


def put(s3, key: str, body: bytes) -> None:
    try:
        s3.put_object(Bucket=BUCKET, Key=key, Body=body)
    except ClientError as exc:
        raise SystemExit(
            f"could not write s3://{BUCKET}/{key}. Run setup_buckets.py first. {exc}"
        ) from exc
    print(f"uploaded s3://{BUCKET}/{key} ({len(body):,} bytes)")


def main() -> None:
    args = parse_args()
    random.seed(args.trade_date)

    n_bad = (args.trades * (DIRTY_BAD_PCT if args.dirty else HAPPY_BAD_PCT)) // 100
    room = args.trades - n_bad - 1
    target_unpriced = DIRTY_UNPRICED if args.dirty else HAPPY_UNPRICED
    n_unpriced = min(target_unpriced, room) if room >= 1 else 0
    if args.dirty and (n_bad / args.trades) < 0.02 and n_unpriced < 100:
        print(
            "warning: --dirty file is too small to fail the quality gate "
            "(need about 20 trades for the reject rate, or 121 for the unpriced count)"
        )

    equities = build_equities(args.market_rows)
    tradable = [row for row in equities if row.status == "ok"]
    portfolios = build_portfolios(args.trade_date, args.positions, equities)
    portfolio_ids = [p["portfolio_id"] for p in portfolios]
    trades = build_trades(
        args.trade_date, args.trades, portfolio_ids, tradable, n_bad, n_unpriced
    )

    date = args.trade_date
    trade_key = f"trades/dt={date}/trades_{date}.txt"
    equity_key = f"market_data/dt={date}/equities.csv"
    fx_key = f"market_data/dt={date}/fx.csv"
    portfolio_key = f"portfolio/dt={date}/portfolio_{date}.json"

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )
    put(s3, trade_key, ("\n".join(trades) + "\n").encode("utf-8"))
    put(s3, equity_key, equities_csv(equities, date).encode("utf-8"))
    put(s3, fx_key, fx_csv(date).encode("utf-8"))
    put(s3, portfolio_key, (json.dumps(portfolios, indent=2) + "\n").encode("utf-8"))

    n_blank = sum(1 for row in equities if row.status == "blank")
    n_nonpositive = sum(1 for row in equities if row.status == "non_positive")
    print(
        f"date={date} mode={'dirty' if args.dirty else 'happy'} "
        f"trades={args.trades} malformed_or_missing_tag={n_bad} "
        f"unpriced_symbol_trades={n_unpriced} "
        f"equities={args.market_rows} blank_closes={n_blank} "
        f"non_positive_closes={n_nonpositive} "
        f"portfolios={len(portfolios)} positions={args.positions}"
    )


if __name__ == "__main__":
    sys.exit(main())
