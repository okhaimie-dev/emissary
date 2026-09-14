#!/usr/bin/env python3
"""
Emissary collector — Robinhood Chain (chain 4663) STONX / ve(3,3) data.

Fetches the public Ekubo API:
  - ve33 pools (votes, fees, volume, liquidity) for the STONX Ve33 extension
  - top pairs (volume / TVL)
  - chain TVL
  - token metadata for every token we see

Stores:
  - raw JSON snapshots in data/snapshots/<ts>/...  (never lose source data)
  - normalized rows in data/emissary.db (SQLite)   (query-friendly history)

Run once:      python3 collector/collect.py
Run hourly:    python3 collector/collect.py --loop 3600
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

API = "https://prod-api.ekubo.org"
CHAIN_ID = 4663  # Robinhood Chain
# STONX Ve33 extension on Robinhood Chain (found via pool configs)
VE33 = "0xd18685a514e59b06d59824e16db07e73345d9953"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SNAP_DIR = os.path.join(DATA_DIR, "snapshots")
DB_PATH = os.path.join(DATA_DIR, "emissary.db")
HISTORY_DIR = os.path.join(DATA_DIR, "history")  # compact per-run files, safe to commit

# STONX bootstrap emissions: ~3,333.33 STONX/day pre-scheduled for ~100 days
# (see ekubo.org/blog "Launch STONX on Robinhood Chain"). Used for efficiency math.
EMISSIONS_DAILY_STONX = 3333.33


def get(path, timeout=30):
    """GET a JSON endpoint with small retry."""
    url = API + path
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "emissary-collector/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed: {url} ({last_err})")


def norm_addr(v):
    """Normalize an EVM address (string or int) to lowercase 0x + 40 hex chars."""
    i = int(v, 16) if isinstance(v, str) else int(v)
    return "0x" + format(i, "040x")


def db():
    os.makedirs(SNAP_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS tokens (
            chain_id INTEGER, address TEXT, symbol TEXT, name TEXT,
            decimals INTEGER, usd_price REAL, updated_at TEXT,
            PRIMARY KEY (chain_id, address));
        CREATE TABLE IF NOT EXISTS ve33_pools (
            ts TEXT, pool_id TEXT, pool_key_id INTEGER,
            token0 TEXT, token1 TEXT, fee TEXT, tick_spacing INTEGER,
            tick INTEGER, liquidity TEXT, vote_weight TEXT, swap_fee TEXT,
            volume0_24h TEXT, volume1_24h TEXT,
            fees0_24h TEXT, fees1_24h TEXT,
            ve33_fees0_24h TEXT, ve33_fees1_24h TEXT,
            ve33_fees0_7d TEXT, ve33_fees1_7d TEXT,
            ve33_fees0_all TEXT, ve33_fees1_all TEXT,
            tvl0_total TEXT, tvl1_total TEXT, depth_percent REAL,
            PRIMARY KEY (ts, pool_id));
        CREATE TABLE IF NOT EXISTS pairs (
            ts TEXT, token0 TEXT, token1 TEXT,
            volume0_24h TEXT, volume1_24h TEXT,
            tvl0_total TEXT, tvl1_total TEXT,
            depth0 TEXT, depth1 TEXT,
            PRIMARY KEY (ts, token0, token1));
        CREATE TABLE IF NOT EXISTS raw_files (
            ts TEXT, name TEXT, path TEXT, PRIMARY KEY (ts, name));
        """
    )
    return con


def save_raw(ts, name, obj):
    d = os.path.join(SNAP_DIR, ts)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".json")
    with open(p, "w") as f:
        json.dump(obj, f)
    return p


def fetch_tokens(con, addresses, ts):
    """Fetch metadata for a set of token addresses (chain 4663), upsert into DB.
    Returns (count, meta) where meta maps normalized address -> token info."""
    got = 0
    meta = {}
    for addr in addresses:
        try:
            t = get(f"/tokens/{CHAIN_ID}/{addr}")
        except RuntimeError:
            continue  # token not in the API catalog — skip
        a = norm_addr(addr)
        con.execute(
            "INSERT OR REPLACE INTO tokens VALUES (?,?,?,?,?,?,?)",
            (CHAIN_ID, a, t.get("symbol"), t.get("name"),
             t.get("decimals"), t.get("usd_price"), ts),
        )
        meta[a] = {"symbol": t.get("symbol"), "decimals": t.get("decimals"),
                   "usd_price": t.get("usd_price")}
        got += 1
    con.commit()
    return got, meta


def write_history(ts, pools, meta):
    """Write a compact, commit-friendly snapshot to data/history/<ts>.json.

    This is the file we commit from GitHub Actions every hour — small (~30-60KB)
    and complete enough to rebuild the dashboard and the weekly reports.
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    keys = ["pool_id", "token0", "token1", "fee", "tick_spacing",
            "pool_total_vote_weight", "swap_fee",
            "volume0_24h", "volume1_24h",
            "ve33_fees0_24h", "ve33_fees1_24h",
            "ve33_fees0_7d", "ve33_fees1_7d",
            "tvl0_total", "tvl1_total", "depth_percent"]
    trim = []
    for p in pools:
        row = {k: p.get(k) for k in keys}
        row["token0"] = norm_addr(p["token0"])
        row["token1"] = norm_addr(p["token1"])
        st = p.get("pool_state") or {}
        row["tick"] = st.get("tick")
        row["liquidity"] = st.get("liquidity")
        trim.append(row)
    out = {
        "ts": ts,
        "chain_id": CHAIN_ID,
        "ve33": VE33,
        "emissions_daily_stonx": EMISSIONS_DAILY_STONX,
        "tokens": meta,
        "pools": trim,
    }
    path = os.path.join(HISTORY_DIR, ts + ".json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return path


def run_once():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    print(f"[{ts}] collecting…")
    con = db()
    con.execute("INSERT OR REPLACE INTO meta VALUES ('last_run', ?)", (ts,))
    con.commit()

    # 1. ve33 pools (the core dataset)
    v = get(f"/ve33/{VE33}/pools?chainId={CHAIN_ID}&pageSize=200")
    pools = v.get("data", [])
    p1 = save_raw(ts, "ve33_pools", v)
    con.execute("INSERT OR REPLACE INTO raw_files VALUES (?,?,?)", (ts, "ve33_pools", p1))
    for p in pools:
        st = p.get("pool_state") or {}
        con.execute(
            """INSERT OR REPLACE INTO ve33_pools VALUES
               (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, p.get("pool_id"), p.get("pool_key_id"),
             norm_addr(p["token0"]), norm_addr(p["token1"]),
             str(p.get("fee")), p.get("tick_spacing"),
             st.get("tick"), st.get("liquidity"),
             str(p.get("pool_total_vote_weight")), str(p.get("swap_fee")),
             str(p.get("volume0_24h")), str(p.get("volume1_24h")),
             str(p.get("fees0_24h")), str(p.get("fees1_24h")),
             str(p.get("ve33_fees0_24h")), str(p.get("ve33_fees1_24h")),
             str(p.get("ve33_fees0_7d")), str(p.get("ve33_fees1_7d")),
             str(p.get("ve33_fees0_all")), str(p.get("ve33_fees1_all")),
             str(p.get("tvl0_total")), str(p.get("tvl1_total")),
             p.get("depth_percent")),
        )
    con.commit()
    print(f"  ve33 pools: {len(pools)}")

    # 2. pairs (volume / TVL breadth)
    pr = get(f"/overview/pairs?chainId={CHAIN_ID}&minTvlUsd=0")
    pairs = pr.get("topPairs", [])
    p2 = save_raw(ts, "pairs", pr)
    con.execute("INSERT OR REPLACE INTO raw_files VALUES (?,?,?)", (ts, "pairs", p2))
    for x in pairs:
        con.execute(
            "INSERT OR REPLACE INTO pairs VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, norm_addr(x["token0"]), norm_addr(x["token1"]),
             str(x.get("volume0_24h")), str(x.get("volume1_24h")),
             str(x.get("tvl0_total")), str(x.get("tvl1_total")),
             str(x.get("depth0")), str(x.get("depth1"))),
        )
    con.commit()
    print(f"  pairs: {len(pairs)}")

    # 3. chain TVL
    tvl = get(f"/overview/tvl?chainId={CHAIN_ID}")
    p3 = save_raw(ts, "tvl", tvl)
    con.execute("INSERT OR REPLACE INTO raw_files VALUES (?,?,?)", (ts, "tvl", p3))
    con.commit()
    print(f"  tvl tokens: {len(tvl.get('tvlByToken', []))}")

    # 4. token metadata for everything we saw
    addrs = set()
    for p in pools:
        addrs.add(p["token0"])
        addrs.add(p["token1"])
    for x in pairs:
        addrs.add(x["token0"])
        addrs.add(x["token1"])
    n = fetch_tokens(con, sorted(addrs), ts)
    print(f"  token metadata: {n[0]}/{len(addrs)}")

    # 5. compact, commit-friendly history snapshot
    hist = write_history(ts, pools, n[1])
    print(f"  history: {hist}")

    # 6. refresh the web dashboard data (best effort)
    try:
        import export_web
        export_web.main()
    except Exception as e:
        print(f"  web export skipped: {e}")

    con.close()
    print(f"[{ts}] done → {DB_PATH}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, metavar="SECONDS",
                    help="keep running every N seconds")
    args = ap.parse_args()
    if args.loop:
        while True:
            try:
                run_once()
            except Exception as e:  # keep the loop alive
                print(f"collector error: {e}", file=sys.stderr)
            time.sleep(args.loop)
    else:
        run_once()


if __name__ == "__main__":
    main()
