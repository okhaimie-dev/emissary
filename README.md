# Emissary (working title)

**Liquidity intelligence for Robinhood Chain's tokenized-stock economy.**

Emissary tracks the STONX ve(3,3) system on Robinhood Chain — the incentives marketplace
that bootstraps liquidity for tokenized stocks (NVDA, AAPL, TSLA, SPY, ...) trading on
Ekubo. Nobody else publishes this data over time.

## What it does (roadmap)

1. **Pools Dashboard** — every STONX pool: vote weight, emissions, fees, voter APR, volume.
2. **Efficiency Radar** — volume and fees bought per $1 of emissions per pool.
3. **Weekly Report** — automated public recap (X / Telegram) of the first 100 days.
4. **Alerts** — vote shifts, APR spikes, new pools, emissions changes.
5. **Copilot** — AI recommendations for voters/LPs, with prepared (signable) transactions.

## Data sources

- Ekubo public API: `https://prod-api.ekubo.org`
  - `/ve33/{ve33Address}/pools?chainId=4663` — votes, fees, volume, liquidity per pool
  - `/overview/pairs?chainId=4663` — pair stats
  - `/overview/tvl?chainId=4663` — TVL
  - `/tokens/{chainId}/{address}` — token metadata and prices
- Robinhood Chain (chain id 4663), EVM, built on Arbitrum Orbit.

## Contracts (Robinhood Chain)

- Core (all chains): `0x00000000000014aA86C5d3c41765bb24e11bd701`
- STONX token: `0x570c5aa79c798e7a418412cc8399ae5bcce570c5`
- Ve33 extension: `0xd18685a514e59b06d59824e16db07e73345d9953`
- USDG: `0x5fc5360d0400a0fd4f2af552add042d716f1d168`

## Layout

```
collector/collect.py   # fetches + snapshots + normalizes into SQLite
data/snapshots/        # raw JSON per run (source of truth)
data/emissary.db       # normalized history (SQLite)
```

## Run

```bash
python3 collector/collect.py            # one snapshot
python3 collector/collect.py --loop 3600  # hourly
```

## First snapshot (2026-09-14)

- 55 ve(3,3) pools covering 30+ tokenized stocks/ETFs
- 24h: ~$803K trading volume, ~$1,079 in fees to STONX voters
- Top incentives pools: ETH/USDG (30% of votes), USDG/SNDK, SPCX/USDG, RDDT/USDG, USDG/INTC
- Emissions: 3,333 STONX/day (≈ $3.3K/day) vs ~$1.1K/day voter fees — an emissions/fees
  ratio of ~3:1 that the Efficiency Radar will track over time.
