import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Chart from "chart.js/auto";
import "./styles.css";

const data = window.TMC_DATA || {};
const {
  DATA_GENERATED = "",
  STATS = {},
  SENSITIVITY = [],
  STRATEGY2 = [],
  POLITICIANS = [],
  HC_SENSITIVITY = [],
  PORTFOLIO = {},
  FILINGS = [],
} = data;

const partyColor = { D: "#60a5fa", R: "#f87171", I: "#a78bfa" };
const chartScale = {
  x: { grid: { color: "#1e293b" }, border: { color: "#334155" } },
  y: {
    grid: { color: "#1e293b" },
    border: { color: "#334155" },
    ticks: { callback: (v) => `+${v}%` },
  },
};

function money(n) {
  return `$${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function signedMoney(n) {
  const value = Number(n || 0);
  return `${value >= 0 ? "+" : "-"}${money(Math.abs(value))}`;
}

function signedPct(n) {
  const value = Number(n || 0);
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function Card({ children, className = "", style }) {
  return (
    <div className={`card ${className}`} style={style}>
      {children}
    </div>
  );
}

function ChartCanvas({ config, height }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return undefined;
    const chart = new Chart(ref.current, config);
    return () => chart.destroy();
  }, [config]);
  return <canvas ref={ref} style={height ? { maxHeight: height } : undefined} />;
}

function Nav() {
  return (
    <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between sticky top-0 z-10" style={{ background: "#0f172aee" }}>
      <div className="flex items-center gap-2">
        <span className="text-emerald-400 font-black text-lg">&#9670;</span>
        <span className="font-bold text-lg tracking-tight">TrackMyCongress</span>
      </div>
      <a href="https://github.com/samsnowy/TrackMyCongress" target="_blank" className="flex items-center gap-2 text-slate-400 hover:text-white text-sm transition-colors" rel="noreferrer">
        GitHub
      </a>
    </nav>
  );
}

function Hero() {
  const hcExcess90 = HC_SENSITIVITY.length ? HC_SENSITIVITY[HC_SENSITIVITY.length - 1].excess : 7.9;
  return (
    <section className="px-6 py-16 max-w-6xl mx-auto">
      <div className="inline-flex items-center gap-2 border rounded-full px-4 py-1.5 text-sm font-medium mb-6" style={{ background: "#10b98115", borderColor: "#10b98133", color: "#34d399" }}>
        <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#34d399" }} />
        Live paper trading on Alpaca - $1M simulated equity
      </div>
      <h1 className="text-5xl md:text-7xl font-black tracking-tight mb-5 leading-none">
        Following the<br /><span style={{ color: "#34d399" }}>Money in Congress</span>
      </h1>
      <p className="text-xl max-w-2xl mb-10 leading-relaxed" style={{ color: "#94a3b8" }}>
        STOCK Act filings are public. We backtested <strong style={{ color: "#f1f5f9" }}>10,000+ trades</strong> from 170 members against SPY.
        Following the 12-politician reliable group beats SPY by <strong style={{ color: "#34d399" }}>+{STATS.avg_excess_90d}%</strong> at 90 days.
        A high-conviction filter showed <strong style={{ color: "#f59e0b" }}>+{hcExcess90}%</strong>, but an audit found structural issues; the live strategy runs the broader group.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat value={`~${Math.round((STATS.total_trades || 0) / 1000).toLocaleString()},000`} label="Stock trades analyzed" />
        <Stat value={STATS.total_options} label="Options trades" />
        <Stat value={`+${STATS.avg_excess_90d}%`} label="90d excess - 12-pol group (live)" color="#34d399" />
        <Stat value={`+${hcExcess90}%`} label="90d excess - HC backtest (research)" color="#f59e0b" />
      </div>
    </section>
  );
}

function Stat({ value, label, color }) {
  return (
    <Card className="p-5">
      <div className="text-3xl font-bold" style={{ color }}>{value}</div>
      <div className="text-sm mt-1" style={{ color: "#94a3b8" }}>{label}</div>
    </Card>
  );
}

function AlphaSection() {
  const politicians = useMemo(() => [...POLITICIANS].sort((a, b) => b.excess - a.excess), []);
  const holdConfig = useMemo(() => ({
    type: "bar",
    data: {
      labels: SENSITIVITY.map((s) => `${s.hold}d`),
      datasets: [
        { label: "Congress (reliable group)", data: SENSITIVITY.map((s) => s.avg_ret), backgroundColor: "#10b981", borderRadius: 4, borderSkipped: false },
        { label: "SPY (same window)", data: SENSITIVITY.map((s) => s.spy), backgroundColor: "#334155", borderRadius: 4, borderSkipped: false },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } } }, scales: chartScale },
  }), []);
  const polConfig = useMemo(() => ({
    type: "bar",
    data: {
      labels: politicians.map((p) => p.name),
      datasets: [{
        label: "Avg Excess Return (90d)",
        data: politicians.map((p) => p.excess),
        backgroundColor: politicians.map((p) => (p.trades >= 80 ? "#10b981" : p.trades >= 30 ? "#34d399" : "#6ee7b7")),
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { ...chartScale, x: { ...chartScale.x, ticks: { maxRotation: 40, minRotation: 30, font: { size: 11 } } } } },
  }), [politicians]);

  return (
    <section className="px-6 py-12 border-t" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto">
        <SectionKicker color="#34d399">Findings 1 &amp; 2</SectionKicker>
        <h2 className="text-3xl md:text-4xl font-bold mb-3">Alpha grows with hold period</h2>
        <p className="max-w-2xl mb-8 leading-relaxed" style={{ color: "#94a3b8" }}>
          Entry at close on the public filing date. {STATS.reliable_count} politicians with avg excess &gt;2% and &gt;=20 trades. Edge is in magnitude: winners win bigger than losers lose.
        </p>
        <div className="grid md:grid-cols-2 gap-6 mb-6">
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-xs font-medium uppercase tracking-wide" style={{ borderColor: "#334155", color: "#64748b" }}>
                {["Hold", "Trades", "Avg Ret", "SPY", "Excess", "Win%"].map((h, i) => <th key={h} className={`${i ? "text-right" : "text-left"} px-5 py-3`}>{h}</th>)}
              </tr></thead>
              <tbody>
                {SENSITIVITY.map((s, i) => (
                  <tr key={s.hold} className={i === SENSITIVITY.length - 1 ? "" : "border-b"} style={{ borderColor: "#0f172a" }}>
                    <td className={`px-5 py-3.5 font-mono ${i === SENSITIVITY.length - 1 ? "font-bold text-white" : "font-medium"}`}>{s.hold}d</td>
                    <td className="text-right px-5 py-3.5" style={{ color: "#94a3b8" }}>{s.trades.toLocaleString()}</td>
                    <td className="text-right px-5 py-3.5">+{s.avg_ret}%</td>
                    <td className="text-right px-5 py-3.5" style={{ color: "#64748b" }}>+{s.spy}%</td>
                    <td className="text-right px-5 py-3.5 font-semibold" style={{ color: "#34d399" }}>+{s.excess}%</td>
                    <td className="text-right px-5 py-3.5" style={{ color: "#cbd5e1" }}>{s.win_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card className="p-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: "#64748b" }}>Avg return vs SPY by hold period</h3>
            <ChartCanvas config={holdConfig} />
          </Card>
        </div>
        <Card className="p-5 mb-6" style={{ borderLeft: "4px solid #34d399" }}>
          <p className="text-sm leading-relaxed" style={{ color: "#cbd5e1" }}>
            <strong className="text-white">Win rate hovers near 50-55% regardless of hold period.</strong> The edge is not in picking direction; it is in the asymmetric return distribution.
          </p>
        </Card>
        <SectionKicker color="#34d399">Finding 2</SectionKicker>
        <h3 className="text-2xl font-bold mb-3">Top performers at 90-day hold</h3>
        <Card className="p-6">
          <ChartCanvas config={polConfig} height={340} />
        </Card>
      </div>
    </section>
  );
}

function OptionsSection() {
  const optionsConfig = useMemo(() => ({
    type: "bar",
    data: {
      labels: ["30d", "60d", "90d"],
      datasets: [
        { label: "Options signal (buy underlying)", data: [3.8, 0.9, 0.8], backgroundColor: "#818cf8", borderRadius: 4, borderSkipped: false },
        { label: "Stock signal (all-trades group)", data: [1.1, 1.8, 2.3], backgroundColor: "#334155", borderRadius: 4, borderSkipped: false },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } } }, scales: chartScale },
  }), []);
  return (
    <section className="px-6 py-12 border-t" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto">
        <SectionKicker color="#34d399">Finding 3</SectionKicker>
        <h2 className="text-3xl md:text-4xl font-bold mb-3">Pelosi and Gottheimer buy synthetic longs</h2>
        <p className="max-w-2xl mb-8 leading-relaxed" style={{ color: "#94a3b8" }}>
          462 options trades across both chambers. The real signal is in deep-ITM House calls.
        </p>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <Metric value="76%" label="of House calls are >20% ITM" />
              <Metric value="+3.8%" label="Excess at 30d buying the underlying" />
              <Metric value="~20" label="Tuberville straddle pairs" muted />
            </div>
            <Card className="overflow-hidden text-sm">
              <div className="px-5 py-3 border-b font-semibold" style={{ borderColor: "#334155" }}>Deep ITM examples - strike/spot at filing</div>
              <table className="w-full">
                <tbody>
                  {[
                    ["Pelosi", "NVDA", "$80", "$137.70", "0.58"],
                    ["Pelosi", "AMZN", "$150", "$225.90", "0.66"],
                    ["Gottheimer", "MSFT", "$320-325", "$424.62", "0.75-0.77"],
                  ].map((row) => (
                    <tr key={row[1]} className="border-b" style={{ borderColor: "#0f172a" }}>
                      {row.map((cell, i) => <td key={i} className={`${i > 1 ? "text-right" : ""} px-5 py-3 ${i === 1 ? "font-mono font-bold" : ""}`}>{cell}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
          <Card className="p-4">
            <h3 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>Options vs stock signal excess by hold period</h3>
            <ChartCanvas config={optionsConfig} />
            <p className="text-xs mt-3" style={{ color: "#64748b" }}>Options signal peaks at 30d. Stock signal builds over 90d.</p>
          </Card>
        </div>
      </div>
    </section>
  );
}

function Strategy2Section() {
  const config = useMemo(() => ({
    type: "bar",
    data: {
      labels: STRATEGY2.map((r) => `+${r.hold_after_sell}d`),
      datasets: [
        { label: "Congress (Strategy 2)", data: STRATEGY2.map((r) => r.avg_ret), backgroundColor: "#f59e0b", borderRadius: 4, borderSkipped: false },
        { label: "SPY (same window)", data: STRATEGY2.map((r) => r.spy), backgroundColor: "#334155", borderRadius: 4, borderSkipped: false },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } } }, scales: chartScale },
  }), []);
  const maxExcess = Math.max(...STRATEGY2.map((r) => r.excess));
  return (
    <section className="px-6 py-12 border-t" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto">
        <SectionKicker color="#f59e0b">Finding 4 - Counterintuitive</SectionKicker>
        <h2 className="text-3xl md:text-4xl font-bold mb-3">Exit 10 days after the sell filing, not before</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-xs uppercase tracking-wide" style={{ borderColor: "#334155", color: "#64748b" }}>
                {["Exit", "Pairs", "Avg Ret", "SPY", "Excess", "Win%"].map((h, i) => <th key={h} className={`${i ? "text-right" : "text-left"} px-5 py-2`}>{h}</th>)}
              </tr></thead>
              <tbody>
                {STRATEGY2.map((r) => {
                  const best = r.excess === maxExcess;
                  return (
                    <tr key={r.hold_after_sell} className="border-b" style={{ borderColor: "#0f172a", background: best ? "#f59e0b08" : undefined }}>
                      <td className={`px-5 py-3.5 font-mono ${best ? "font-bold text-white" : ""}`}>+{r.hold_after_sell}d{best ? " <-" : ""}</td>
                      <td className="text-right px-5 py-3.5" style={{ color: "#94a3b8" }}>{r.pairs}</td>
                      <td className="text-right px-5 py-3.5">+{r.avg_ret}%</td>
                      <td className="text-right px-5 py-3.5" style={{ color: "#64748b" }}>+{r.spy}%</td>
                      <td className="text-right px-5 py-3.5 font-semibold" style={{ color: "#f59e0b" }}>+{r.excess}%</td>
                      <td className="text-right px-5 py-3.5" style={{ color: "#cbd5e1" }}>{r.win_pct}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
          <Card className="p-4">
            <h3 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "#64748b" }}>Excess return vs SPY by exit timing</h3>
            <ChartCanvas config={config} />
          </Card>
        </div>
      </div>
    </section>
  );
}

function FilingsSection() {
  const [mode, setMode] = useState("all");
  const [page, setPage] = useState(0);
  const pageSize = 20;
  const rows = useMemo(() => {
    let result = FILINGS;
    if (mode === "purchase") result = result.filter((r) => r.txn === "Purchase");
    if (mode === "sale") result = result.filter((r) => r.txn === "Sale");
    if (mode === "options") result = result.filter((r) => r.type === "OP");
    if (mode === "reliable") result = result.filter((r) => r.reliable);
    if (mode === "signals") result = result.filter((r) => r.reliable && r.txn === "Purchase");
    if (mode === "hcsignals") result = result.filter((r) => r.hc && r.txn === "Purchase");
    return result;
  }, [mode]);
  useEffect(() => setPage(0), [mode]);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pageRows = rows.slice(page * pageSize, page * pageSize + pageSize);
  const filters = [["all", "All"], ["purchase", "Purchases"], ["sale", "Sales"], ["options", "Options"], ["reliable", "Reliable group"], ["signals", "Buy signals"], ["hcsignals", "HC signals"]];

  return (
    <section className="px-6 py-12 border-t" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto">
        <SectionKicker color="#34d399">Static Snapshot</SectionKicker>
        <h2 className="text-3xl md:text-4xl font-bold mb-1">Recent STOCK Act filings</h2>
        <p className="max-w-2xl mb-6 leading-relaxed" style={{ color: "#94a3b8" }}>Last 90 days from the Quiver Quant feed. <span style={{ color: "#64748b" }}>Snapshot: {DATA_GENERATED}.</span></p>
        <div className="flex flex-wrap gap-2 mb-4">
          {filters.map(([id, label]) => (
            <button key={id} onClick={() => setMode(id)} className={`filing-filter ${mode === id ? "active-filter" : ""} px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors`}>{label}</button>
          ))}
        </div>
        <Card className="overflow-hidden">
          <div style={{ overflowX: "auto" }}>
            <table className="w-full text-sm">
              <thead><tr style={{ background: "#0f172a", borderBottom: "1px solid #334155" }}>
                {["Filed", "Traded", "Member", "Ticker", "Action", "Size", "Signal?"].map((h) => <th key={h} className="text-left px-4 py-3 font-semibold" style={{ color: "#64748b", whiteSpace: "nowrap" }}>{h}</th>)}
              </tr></thead>
              <tbody>{pageRows.map((r, i) => <FilingRow key={`${r.date}-${r.name}-${r.ticker}-${i}`} row={r} index={i} />)}</tbody>
            </table>
          </div>
        </Card>
        <div className="flex items-center justify-between mt-3 text-sm">
          <div style={{ color: "#64748b" }}>Showing {rows.length ? page * pageSize + 1 : 0}-{Math.min((page + 1) * pageSize, rows.length)} of {rows.length}</div>
          <div className="flex items-center gap-2">
            <button disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} className="px-3 py-1.5 rounded border text-xs font-semibold" style={{ background: "#1e293b", borderColor: "#334155", color: "#94a3b8", opacity: page === 0 ? 0.35 : 1 }}>Prev</button>
            <span style={{ color: "#94a3b8", minWidth: 80, textAlign: "center" }}>Page {page + 1} of {totalPages}</span>
            <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} className="px-3 py-1.5 rounded border text-xs font-semibold" style={{ background: "#1e293b", borderColor: "#334155", color: "#94a3b8", opacity: page >= totalPages - 1 ? 0.35 : 1 }}>Next</button>
          </div>
        </div>
      </div>
    </section>
  );
}

function FilingRow({ row, index }) {
  const isBuy = row.txn === "Purchase";
  return (
    <tr style={{ background: index % 2 ? "#0f172a40" : undefined, opacity: row.low_conv ? 0.45 : 1 }}>
      <td className="px-4 py-2.5 font-mono text-xs" style={{ color: "#94a3b8", whiteSpace: "nowrap" }}>{row.date}</td>
      <td className="px-4 py-2.5 font-mono text-xs" style={{ color: "#64748b", whiteSpace: "nowrap" }}>{row.tx_date}</td>
      <td className="px-4 py-2.5" style={{ whiteSpace: "nowrap" }}><span style={{ display: "inline-flex", alignItems: "center" }}><span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: partyColor[row.party] || "#64748b", marginRight: 5, flexShrink: 0 }} /><span style={{ color: "#cbd5e1" }}>{row.name}</span></span></td>
      <td className="px-4 py-2.5 font-mono font-bold" style={{ color: "#f1f5f9" }}>{row.ticker}{row.type === "OP" && <span style={{ background: "#818cf820", color: "#818cf8", padding: "1px 6px", borderRadius: 9999, fontSize: 10, fontWeight: 600, marginLeft: 4 }}>OPT</span>}</td>
      <td className="px-4 py-2.5"><span style={{ background: isBuy ? "#10b98120" : "#ef444420", color: isBuy ? "#34d399" : "#f87171", padding: "2px 8px", borderRadius: 9999, fontSize: 11, fontWeight: 600 }}>{isBuy ? "BUY" : "SELL"}</span></td>
      <td className="px-4 py-2.5 text-xs" style={{ color: "#94a3b8", whiteSpace: "nowrap" }}>{row.range}{row.low_conv && <span style={{ color: "#475569", fontSize: 10 }}> Low conv</span>}</td>
      <td className="px-4 py-2.5 text-center">{row.reliable ? <span title="Reliable group" style={{ color: "#fbbf24", fontSize: 13 }}>&#9733;</span> : <span style={{ color: "#334155" }}>-</span>}</td>
    </tr>
  );
}

function LiveStrategySection() {
  const positions = PORTFOLIO.positions || [];
  const totalPl = Number(PORTFOLIO.total_pl || 0);
  return (
    <section className="px-6 py-12 border-t" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto">
        <SectionKicker color="#818cf8">Live Strategy</SectionKicker>
        <h2 className="text-3xl md:text-4xl font-bold mb-3">Running on Alpaca paper trading</h2>
        <p className="max-w-2xl mb-8 leading-relaxed" style={{ color: "#94a3b8" }}>$1,000,000 simulated equity. Two signal types, one execution path.</p>
        <div className="grid md:grid-cols-2 gap-6 mb-5">
          <StrategyCard title="Stock Signal - All Trades" badge="S" color="#f59e0b" lines={["Quiver live feed, 7-day lookback", "12 reliable politicians", "Same ticker deduped into one signal", "90 days - +4.8% avg excess"]} />
          <StrategyCard title="Options Signal" badge="O" color="#818cf8" lines={["Quiver TickerType==OP, 30-day lookback", "Gottheimer / Pelosi / Ross / Bresnahan", "Deep ITM call purchases", "30 days - +3.8% avg excess"]} />
        </div>
        <Card className="p-4 text-sm flex flex-wrap gap-x-8 gap-y-2" style={{ background: "#1e293b80" }}>
          <div><span style={{ color: "#64748b" }}>Sizing</span> <span className="font-semibold ml-2">5% of equity per position</span></div>
          <div><span style={{ color: "#64748b" }}>Max positions</span> <span className="font-semibold ml-2">15</span></div>
          <div><span style={{ color: "#64748b" }}>Idle cash</span> <span className="font-semibold ml-2">Parked in SPY, 1% cash buffer</span></div>
        </Card>
        <div className="grid md:grid-cols-4 gap-4 mt-5">
          <Stat value={money(PORTFOLIO.equity)} label="Equity" />
          <Stat value={`${signedMoney(totalPl)} (${signedPct(PORTFOLIO.total_pl_pct)})`} label="Total P&L" color={totalPl >= 0 ? "#34d399" : "#f87171"} />
          <Stat value={money(PORTFOLIO.cash)} label="Cash" />
          <Stat value={money(PORTFOLIO.market_value)} label="Invested" />
        </div>
        <Card className="overflow-hidden mt-5">
          <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: "#1e293b" }}>
            <h3 className="font-semibold">Current portfolio</h3>
            <span className="text-xs" style={{ color: "#64748b" }}>{positions.length} positions - {PORTFOLIO.as_of}</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="w-full text-sm">
              <thead style={{ background: "#0f172a", color: "#64748b" }}><tr>{["Ticker", "Role", "Qty", "Avg entry", "Current", "Value", "P&L"].map((h, i) => <th key={h} className={`${i > 1 ? "text-right" : "text-left"} px-4 py-2 font-medium`}>{h}</th>)}</tr></thead>
              <tbody>{positions.map((p, i) => <PortfolioRow key={p.ticker} position={p} index={i} />)}</tbody>
            </table>
          </div>
        </Card>
      </div>
    </section>
  );
}

function StrategyCard({ title, badge, color, lines }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: `${color}20`, color }}>{badge}</div>
        <h3 className="font-semibold">{title}</h3>
      </div>
      <div className="space-y-2.5 text-sm">{lines.map((line, i) => <div key={line} className={`flex gap-3 ${i === lines.length - 1 ? "pt-2 border-t" : ""}`} style={{ borderColor: "#334155" }}><span className="w-16 shrink-0" style={{ color: "#64748b" }}>{i === 0 ? "Source" : i === 1 ? "Filter" : i === 2 ? "Rule" : "Hold"}</span><span className={i === lines.length - 1 ? "font-bold text-white" : ""}>{line}</span></div>)}</div>
    </Card>
  );
}

function PortfolioRow({ position, index }) {
  const pl = Number(position.unrealized_pl || 0);
  return (
    <tr style={{ background: index % 2 ? "#0f172a40" : undefined }}>
      <td className="px-4 py-2.5 font-mono font-bold" style={{ color: "#f1f5f9" }}>{position.ticker}</td>
      <td className="px-4 py-2.5" style={{ color: "#cbd5e1" }}>{position.role === "parking" ? "SPY parking" : "Signal"}</td>
      <td className="px-4 py-2.5 text-right font-mono" style={{ color: "#cbd5e1" }}>{Number(position.qty || 0).toLocaleString()}</td>
      <td className="px-4 py-2.5 text-right font-mono" style={{ color: "#cbd5e1" }}>${Number(position.avg_entry || 0).toFixed(2)}</td>
      <td className="px-4 py-2.5 text-right font-mono" style={{ color: "#cbd5e1" }}>${Number(position.current_price || 0).toFixed(2)}</td>
      <td className="px-4 py-2.5 text-right font-mono" style={{ color: "#cbd5e1" }}>{money(position.market_value)}</td>
      <td className="px-4 py-2.5 text-right font-mono font-semibold" style={{ color: pl >= 0 ? "#34d399" : "#f87171" }}>{signedMoney(pl)} <span style={{ fontSize: 11 }}>({signedPct(position.unrealized_pct)})</span></td>
    </tr>
  );
}

function CaveatsSection() {
  return (
    <section className="px-6 py-12 border-t" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto">
        <SectionKicker color="#64748b">Before you trade on any of this</SectionKicker>
        <h2 className="text-3xl md:text-4xl font-bold mb-8">Caveats &amp; validation</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <Caveat title="In-sample selection bias" color="#f59e0b">The reliable politicians were selected from the same 2022-2026 data the backtest runs on. Selection inflates apparent returns.</Caveat>
          <Caveat title="Backtesting assumptions" color="#f59e0b">Returns assume buying at the close on the filing date with zero slippage. STOCK Act data is self-reported with known errors.</Caveat>
          <Caveat title="Walk-forward test" color="#34d399">Train on 2022-2023, test on 2024-2026. All-trades retained some alpha; HC retained more, with structural caveats.</Caveat>
          <Caveat title="Remaining validations" color="#60a5fa">Permutation tests, transaction cost sensitivity, and beta-adjusted alpha still matter before taking this beyond paper trading.</Caveat>
        </div>
      </div>
    </section>
  );
}

function Caveat({ title, color, children }) {
  return (
    <Card className="p-5" style={{ borderLeft: `4px solid ${color}` }}>
      <h3 className="font-semibold mb-2" style={{ color }}>{title}</h3>
      <p className="text-sm leading-relaxed" style={{ color: "#94a3b8" }}>{children}</p>
    </Card>
  );
}

function Metric({ value, label, muted }) {
  return (
    <Card className="p-4 text-center">
      <div className="text-3xl font-bold mb-1" style={{ color: muted ? "#cbd5e1" : "#34d399" }}>{value}</div>
      <div className="text-xs" style={{ color: "#94a3b8" }}>{label}</div>
    </Card>
  );
}

function SectionKicker({ children, color }) {
  return <div className="text-xs font-semibold tracking-widest uppercase mb-2" style={{ color }}>{children}</div>;
}

function Footer() {
  return (
    <footer className="border-t px-6 py-10" style={{ borderColor: "#1e293b" }}>
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div>
          <div className="font-bold text-lg mb-1">TrackMyCongress</div>
          <div className="text-sm" style={{ color: "#64748b" }}>Research tool for congressional stock disclosure analysis. House &amp; Senate 2022-2026.</div>
          <div className="text-xs mt-1.5" style={{ color: "#475569" }}>Not financial advice. Python, yfinance, pandas, Alpaca SDK, Quiver Quant.</div>
        </div>
        <a href="https://github.com/samsnowy/TrackMyCongress" target="_blank" rel="noreferrer" className="card flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:border-slate-500">View source on GitHub</a>
      </div>
    </footer>
  );
}

function App() {
  return (
    <>
      <Nav />
      <Hero />
      <AlphaSection />
      <OptionsSection />
      <Strategy2Section />
      <FilingsSection />
      <LiveStrategySection />
      <CaveatsSection />
      <Footer />
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
