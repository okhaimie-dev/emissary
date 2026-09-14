import { useEffect, useMemo, useState } from "react";

const STONX = "0x570c5aa79c798e7a418412cc8399ae5bcce570c5";

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const usdFmt = (n) =>
  n == null ? "—" : (n < 0 ? "-$" : "$") + compact.format(Math.abs(n));

function shortAddr(a) {
  return a ? a.slice(0, 6) + "…" + a.slice(-4) : "?";
}

function tokenValue(raw, tok) {
  if (raw == null || !tok || tok.usd_price == null || !tok.decimals) return null;
  const n = Number(raw) / 10 ** tok.decimals * tok.usd_price;
  return Number.isFinite(n) ? n : null;
}

function PoolPair({ t0, t1 }) {
  const s0 = t0?.symbol || shortAddr(t0?.address);
  const s1 = t1?.symbol || shortAddr(t1?.address);
  return (
    <span className="font-medium">
      {s0}
      <span className="text-zinc-500"> / </span>
      {s1}
    </span>
  );
}

function StatCard({ label, value, sub, tone = "zinc" }) {
  const tones = {
    zinc: "text-zinc-100",
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    sky: "text-sky-400",
  };
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`tabular mt-1 text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

function EfficiencyBar({ eff }) {
  const width = Math.min(100, (eff / 2) * 100);
  const color = eff >= 1 ? "bg-emerald-500" : eff >= 0.3 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-800">
      <div className={`h-full ${color}`} style={{ width: `${width}%` }} />
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [sortKey, setSortKey] = useState("votes");
  const [direction, setDirection] = useState("desc");

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/latest.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const view = useMemo(() => {
    if (!data) return null;
    const tokens = data.tokens || {};
    const stonx = tokens[STONX];
    const stonxPrice = stonx?.usd_price ?? 1;
    const emissionsUsd = (data.emissions_daily_stonx || 0) * stonxPrice;

    const pools = (data.pools || [])
      .map((p) => {
        const t0 = tokens[p.token0];
        const t1 = tokens[p.token1];
        const voteWeight = Number(p.pool_total_vote_weight || 0);
        const vol = (tokenValue(p.volume0_24h, t0) || 0) + (tokenValue(p.volume1_24h, t1) || 0);
        const fees = (tokenValue(p.ve33_fees0_24h, t0) || 0) + (tokenValue(p.ve33_fees1_24h, t1) || 0);
        const tvl = (tokenValue(p.tvl0_total, t0) || 0) + (tokenValue(p.tvl1_total, t1) || 0);
        const fees7d = (tokenValue(p.ve33_fees0_7d, t0) || 0) + (tokenValue(p.ve33_fees1_7d, t1) || 0);
        return { p, t0, t1, voteWeight, vol, fees, fees7d, tvl };
      })
      .filter((r) => r.voteWeight > 0 || r.vol > 0 || r.tvl > 0);

    const totalVotes = pools.reduce((s, r) => s + r.voteWeight, 0) || 1;
    pools.forEach((r) => {
      r.share = r.voteWeight / totalVotes;
      r.emissions = (data.emissions_daily_stonx || 0) * r.share;
      r.emissionsUsd = emissionsUsd * r.share;
      r.eff = r.emissionsUsd > 0 ? r.fees / r.emissionsUsd : null;
      r.apr = r.tvl > 0 ? (r.fees * 365 * 100) / r.tvl : null;
      r.symbol0 = r.t0?.symbol || shortAddr(r.p.token0);
      r.symbol1 = r.t1?.symbol || shortAddr(r.p.token1);
    });

    const totalVol = pools.reduce((s, r) => s + r.vol, 0);
    const totalFees = pools.reduce((s, r) => s + r.fees, 0);
    const totalTvl = pools.reduce((s, r) => s + r.tvl, 0);
    const stockCount = new Set(
      pools
        .flatMap((r) => [r.symbol0, r.symbol1])
        .filter((s) => s && !["ETH", "WETH", "STONX", "USDG", "USDC", "USDT"].includes(s.toUpperCase()) &&
          !s.startsWith("0x") && s.length <= 6)
    ).size;

    const sorted = [...pools].sort((a, b) => {
      const key = { votes: "voteWeight", volume: "vol", fees: "fees", eff: "eff", tvl: "tvl", apr: "apr" }[sortKey] || "voteWeight";
      const av = a[key] ?? -Infinity;
      const bv = b[key] ?? -Infinity;
      return direction === "desc" ? bv - av : av - bv;
    });

    return { pools, sorted, totalVotes, totalVol, totalFees, totalTvl, emissionsUsd, stonxPrice, stockCount, ts: data.ts };
  }, [data, sortKey, direction]);

  if (error)
    return (
      <div className="mx-auto max-w-3xl p-10">
        <h1 className="text-xl font-semibold">Could not load data</h1>
        <p className="mt-2 text-zinc-400">
          {error}. Run <code className="rounded bg-zinc-800 px-1.5 py-0.5">python3 collector/export_web.py</code> to generate it.
        </p>
      </div>
    );

  if (!view)
    return <div className="p-10 text-zinc-500">Loading Emissary…</div>;

  const headers = [
    ["Pool", null],
    ["Votes", "votes"],
    ["Emissions / day", null],
    ["24h Volume", "volume"],
    ["Voter fees 24h", "fees"],
    ["Fees per $1 emitted", "eff"],
    ["TVL", "tvl"],
    ["Fee APR", "apr"],
  ];

  const toggleSort = (key) => {
    if (!key) return;
    if (sortKey === key) setDirection(direction === "desc" ? "asc" : "desc");
    else {
      setSortKey(key);
      setDirection("desc");
    }
  };

  const updated = view.ts ? new Date(view.ts).toLocaleString("en-US", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" }) + " UTC" : "";

  return (
    <div className="mx-auto max-w-7xl px-5 py-8">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">Emissary</h1>
            <span className="rounded-full border border-emerald-700/60 bg-emerald-900/30 px-2.5 py-0.5 text-xs font-medium text-emerald-300">
              Robinhood Chain
            </span>
          </div>
          <p className="mt-1 text-sm text-zinc-400">
            Liquidity intelligence for tokenized stocks — tracking the first 100 days of STONX
            ve(3,3) incentives on Ekubo.
          </p>
        </div>
        <div className="text-right text-xs text-zinc-500">
          <div>Updated {updated}</div>
          <div className="mt-1">55 pools · 30+ stock-token markets · hourly snapshots</div>
        </div>
      </header>

      {/* Stats */}
      <section className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard label="24h volume" value={usdFmt(view.totalVol)} sub="all ve(3,3) pools" tone="sky" />
        <StatCard label="Voter fees 24h" value={usdFmt(view.totalFees)} sub="fees earned by STONX voters" tone="emerald" />
        <StatCard label="Emissions / day" value={usdFmt(view.emissionsUsd)} sub={`${data.emissions_daily_stonx?.toFixed(0)} STONX @ $${view.stonxPrice?.toFixed(3)}`} tone="amber" />
        <StatCard
          label="System efficiency"
          value={view.emissionsUsd > 0 ? (view.totalFees / view.emissionsUsd).toFixed(2) : "—"}
          sub="$ fees per $1 of emissions"
          tone={view.totalFees / view.emissionsUsd >= 1 ? "emerald" : "amber"}
        />
        <StatCard label="TVL tracked" value={usdFmt(view.totalTvl)} sub={`${view.pools.length} pools`} />
      </section>

      {/* Explainer */}
      <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-400">
        <span className="font-medium text-zinc-200">How to read this:</span>{" "}
        STONX voters direct a fixed daily emissions budget across pools and earn that pool's trading
        fees. <span className="text-emerald-400">Fees per $1 emitted</span> shows which pools turn
        incentives into real activity — the metric nobody publishes. Above 1.0 means a pool earns
        more in fees than it costs to incentivize.
      </section>

      {/* Table */}
      <section className="mt-6 overflow-hidden rounded-xl border border-zinc-800">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/80 text-left text-xs uppercase tracking-wider text-zinc-500">
                {headers.map(([label, key]) => (
                  <th
                    key={label}
                    onClick={() => toggleSort(key)}
                    className={`px-4 py-3 font-medium ${key ? "cursor-pointer select-none hover:text-zinc-300" : ""} ${
                      ["Votes", "Emissions / day", "24h Volume", "Voter fees 24h", "Fees per $1 emitted", "TVL", "Fee APR"].includes(label) ? "text-right" : ""
                    }`}
                  >
                    {label}
                    {sortKey === key ? (direction === "desc" ? " ↓" : " ↑") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/70">
              {view.sorted.map((r) => {
                const effTone =
                  r.eff == null
                    ? "text-zinc-500"
                    : r.eff >= 1
                    ? "text-emerald-400"
                    : r.eff >= 0.3
                    ? "text-amber-400"
                    : "text-rose-400";
                return (
                  <tr key={r.p.pool_id} className="bg-zinc-950/40 hover:bg-zinc-900/60">
                    <td className="px-4 py-2.5">
                      <PoolPair t0={r.t0} t1={r.t1} />
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">{(r.share * 100).toFixed(1)}%</td>
                    <td className="tabular px-4 py-2.5 text-right text-zinc-400">
                      {r.emissions ? `${compact.format(r.emissions)} STONX` : "—"}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right">{usdFmt(r.vol)}</td>
                    <td className="tabular px-4 py-2.5 text-right">{usdFmt(r.fees)}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-2">
                        <span className={`tabular ${effTone}`}>{r.eff == null ? "—" : r.eff.toFixed(2)}</span>
                        <EfficiencyBar eff={r.eff ?? 0} />
                      </div>
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-zinc-400">{usdFmt(r.tvl)}</td>
                    <td className="tabular px-4 py-2.5 text-right text-zinc-400">
                      {r.apr == null ? "—" : `${r.apr.toFixed(0)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-800 pt-5 text-xs text-zinc-500">
        <div>
          Data: Ekubo public API · Robinhood Chain (4663) · STONX ve(3,3) extension{" "}
          <code className="rounded bg-zinc-900 px-1 py-0.5">0xd186…9953</code>
        </div>
        <div className="flex items-center gap-4">
          <a className="hover:text-zinc-300" href="https://github.com/okhaimie-dev/emissary">
            GitHub
          </a>
          <span>Not financial advice</span>
        </div>
      </footer>
    </div>
  );
}
