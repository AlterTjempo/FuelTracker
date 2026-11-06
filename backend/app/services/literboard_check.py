"""How long should the Literboard stability window be?

    python -m app.services.literboard_check [--fuel e5]

Fair test with the gap held constant: the TARGET is every station's stability in the
last 30 days; the PREDICTOR is its stability in a window of W days that ends right
before that target. The rank correlation (Spearman) between predictor and target says
how well a window of length W predicts the recent behaviour. A longer window is only
worth it if this goes up (more data, less noise) and not down (older behaviour that
no longer applies).
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analytics_config as cfg  # noqa: E402


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a: list[float], b: list[float]):
    if len(a) < 5:
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else None


def swing_ratios(db, column, start, end) -> dict[str, float]:
    from sqlalchemy import func

    from models import FuelPrice

    local_day = func.date(func.timezone("Europe/Berlin", FuelPrice.timestamp))
    daily = (
        db.query(
            FuelPrice.station_id.label("sid"),
            (func.max(column) - func.min(column)).label("rng"),
            func.count(FuelPrice.id).label("n"),
        )
        .filter(
            FuelPrice.timestamp >= start, FuelPrice.timestamp < end, column.isnot(None)
        )
        .group_by(FuelPrice.station_id, local_day)
        .subquery()
    )
    rows = (
        db.query(daily.c.sid, func.avg(daily.c.rng), func.count())
        .filter(daily.c.n >= cfg.LITERBOARD_MIN_ROWS_PER_DAY)
        .group_by(daily.c.sid)
        .all()
    )
    swings = {
        sid: float(avg)
        for sid, avg, days in rows
        if days >= cfg.LITERBOARD_MIN_STABILITY_DAYS
    }
    med = median(swings.values()) if swings else None
    return {sid: v / med for sid, v in swings.items()} if med else {}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuel", default="e5", choices=["e5", "e10", "diesel"])
    args = ap.parse_args(argv)
    from database import SessionLocal
    from models import FuelPrice

    column = {"e5": FuelPrice.e5, "e10": FuelPrice.e10, "diesel": FuelPrice.diesel}[
        args.fuel
    ]
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    target = swing_ratios(db, column, now - timedelta(days=30), now)
    print(
        "| Predictor window (days) | Stations in both | Rank correlation with the last 30 days |"
    )
    print("|---:|---:|---:|")
    for w in (30, 60, 90):
        pred = swing_ratios(
            db, column, now - timedelta(days=30 + w), now - timedelta(days=30)
        )
        common = sorted(set(pred) & set(target))
        rho = spearman([pred[s] for s in common], [target[s] for s in common])
        print(f"| {w} | {len(common)} | {'–' if rho is None else f'{rho:.2f}'} |")
    db.close()


if __name__ == "__main__":
    main()
