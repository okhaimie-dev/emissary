#!/usr/bin/env python3
"""Export the latest snapshot (and a compact time series) for the web dashboard.

Usage:  python3 collector/export_web.py
Writes: dashboard/public/data/latest.json
        dashboard/public/data/series.json
"""

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(ROOT, "data", "history")
OUT = os.path.join(ROOT, "dashboard", "public", "data")


def load(path):
    with open(path) as f:
        return json.load(f)


def usd(raw, tok):
    if raw is None or not tok or tok.get("usd_price") is None or not tok.get("decimals"):
        return 0.0
    return float(raw) / (10 ** tok["decimals"]) * tok["usd_price"]


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(HISTORY, "*.json")))
    if not files:
        print("no history files found — run collector/collect.py first")
        return

    latest = load(files[-1])
    with open(os.path.join(OUT, "latest.json"), "w") as f:
        json.dump(latest, f, separators=(",", ":"))

    series = []
    for path in files:
        d = load(path)
        tokens = d.get("tokens", {})
        vol = fees = 0.0
        for p in d.get("pools", []):
            vol += usd(p.get("volume0_24h"), tokens.get(p.get("token0"))) + usd(p.get("volume1_24h"), tokens.get(p.get("token1")))
            fees += usd(p.get("ve33_fees0_24h"), tokens.get(p.get("token0"))) + usd(p.get("ve33_fees1_24h"), tokens.get(p.get("token1")))
        series.append({
            "ts": d.get("ts"),
            "pools": len(d.get("pools", [])),
            "volume_usd_24h": round(vol, 2),
            "voter_fees_usd_24h": round(fees, 2),
            "emissions_usd_daily": round(
                (d.get("emissions_daily_stonx") or 0)
                * ((tokens.get("0x570c5aa79c798e7a418412cc8399ae5bcce570c5") or {}).get("usd_price") or 0),
                2,
            ),
        })
    with open(os.path.join(OUT, "series.json"), "w") as f:
        json.dump(series, f, separators=(",", ":"))

    print(f"latest: {os.path.basename(files[-1])}")
    print(f"series: {len(series)} snapshots → {OUT}")


if __name__ == "__main__":
    main()
