// All chart and table rendering for TrackMyCongress.
// Depends on: data.js (STATS, SENSITIVITY, POLITICIANS, STRATEGY2, FILINGS, DATA_GENERATED)
// and Chart.js loaded before this file.

const partyColor = { D: '#60a5fa', R: '#f87171', I: '#a78bfa' };

// ── Stats / counters ──────────────────────────────────────────────────────────
document.getElementById('stat-total-trades').textContent = '~' + Math.round(STATS.total_trades / 1000) + ',000';
document.getElementById('stat-total-options').textContent = STATS.total_options;
document.getElementById('stat-avg-excess').textContent   = '+' + STATS.avg_excess_90d + '%';
document.getElementById('hero-avg-excess').textContent   = '+' + STATS.avg_excess_90d + '%';

var hcExcess90 = (typeof HC_SENSITIVITY !== 'undefined' && HC_SENSITIVITY.length)
  ? HC_SENSITIVITY[HC_SENSITIVITY.length - 1].excess : 7.9;
document.getElementById('stat-hc-excess').textContent = '+' + hcExcess90 + '%';
document.getElementById('hero-hc-excess').textContent = '+' + hcExcess90 + '%';
document.getElementById('snapshot-date').textContent = 'Snapshot: ' + DATA_GENERATED + '.';

['caption-reliable-count','subtitle-reliable-count','method-reliable-count','caveat-reliable-count']
  .forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.textContent = STATS.reliable_count;
  });
document.querySelectorAll('.reliable-count').forEach(function(el) {
  el.textContent = STATS.reliable_count;
});

// ── Sensitivity table ─────────────────────────────────────────────────────────
(function() {
  var tbody = document.getElementById('sensitivityBody');
  if (!tbody) return;
  tbody.innerHTML = SENSITIVITY.map(function(s, i) {
    var isLast = i === SENSITIVITY.length - 1;
    var bold   = isLast ? 'font-bold text-white' : 'font-medium';
    var exBold = isLast ? 'font-bold text-base'  : 'font-semibold';
    var border = isLast ? '' : 'border-b';
    return '<tr class="' + border + '" style="border-color:#0f172a">'
      + '<td class="px-5 py-3.5 font-mono ' + bold + '">' + s.hold + 'd</td>'
      + '<td class="text-right px-5 py-3.5 ' + (isLast ? 'font-semibold' : '') + '" style="color:#94a3b8">' + s.trades.toLocaleString() + '</td>'
      + '<td class="text-right px-5 py-3.5 ' + (isLast ? 'font-semibold' : '') + '">+' + s.avg_ret + '%</td>'
      + '<td class="text-right px-5 py-3.5" style="color:#64748b">+' + s.spy + '%</td>'
      + '<td class="text-right px-5 py-3.5 ' + exBold + '" style="color:#34d399">+' + s.excess + '%</td>'
      + '<td class="text-right px-5 py-3.5" style="color:#cbd5e1">' + s.win_pct + '%</td>'
      + '</tr>';
  }).join('');
})();

// ── Strategy 2 table ──────────────────────────────────────────────────────────
(function() {
  if (typeof STRATEGY2 === 'undefined' || !STRATEGY2.length) return;
  var maxExcess = Math.max.apply(null, STRATEGY2.map(function(r) { return r.excess; }));
  var tbody = document.getElementById('strategy2Body');
  if (!tbody) return;
  tbody.innerHTML = STRATEGY2.map(function(r, i) {
    var isBest = r.excess === maxExcess;
    var isLast = i === STRATEGY2.length - 1;
    var bold   = isBest ? 'font-bold text-white' : 'font-medium';
    var exBold = isBest ? 'font-bold text-base'  : 'font-semibold';
    var border = isLast ? '' : 'border-b';
    var mark   = isBest ? ' &larr;' : '';
    return '<tr class="' + border + '" style="border-color:#0f172a' + (isBest ? ';background:#f59e0b08' : '') + '">'
      + '<td class="px-5 py-3.5 font-mono ' + bold + '">+' + r.hold_after_sell + 'd' + mark + '</td>'
      + '<td class="text-right px-5 py-3.5" style="color:#94a3b8">' + r.pairs + '</td>'
      + '<td class="text-right px-5 py-3.5 ' + (isBest ? 'font-semibold' : '') + '">+' + r.avg_ret + '%</td>'
      + '<td class="text-right px-5 py-3.5" style="color:#64748b">+' + r.spy + '%</td>'
      + '<td class="text-right px-5 py-3.5 ' + exBold + '" style="color:#f59e0b">+' + r.excess + '%</td>'
      + '<td class="text-right px-5 py-3.5" style="color:#cbd5e1">' + r.win_pct + '%</td>'
      + '</tr>';
  }).join('');
})();

// ── Filings table ─────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function money(n) {
  return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function signedMoney(n) {
  var v = Number(n || 0);
  return (v >= 0 ? '+' : '-') + money(Math.abs(v));
}

function signedPct(n) {
  var v = Number(n || 0);
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
}

var PAGE_SIZE = 20;
var _currentRows = FILINGS;
var _currentPage = 0;

function renderFilings(rows) { _currentRows = rows; _currentPage = 0; renderPage(); }

function renderPage() {
  var start = _currentPage * PAGE_SIZE;
  var end   = Math.min(start + PAGE_SIZE, _currentRows.length);
  var page  = _currentRows.slice(start, end);
  var tbody = document.getElementById('filingsBody');
  tbody.innerHTML = page.map(function(r, i) {
    var isBuy  = r.txn === 'Purchase';
    var isOpt  = r.type === 'OP';
    var isExec = r.source === 'Executive' || r.type === 'EX';
    var rowBg  = i % 2 === 0 ? '' : 'style="background:#0f172a40"';
    var dim    = r.low_conv ? 'opacity:0.45' : '';
    var txnBadge = isBuy
      ? '<span style="background:#10b98120;color:#34d399;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600">BUY</span>'
      : '<span style="background:#ef444420;color:#f87171;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600">SELL</span>';
    var optBadge = isOpt
      ? ' <span style="background:#818cf820;color:#818cf8;padding:1px 6px;border-radius:9999px;font-size:10px;font-weight:600">OPT</span>'
      : '';
    var execBadge = isExec
      ? ' <span style="background:#f59e0b20;color:#fbbf24;padding:1px 6px;border-radius:9999px;font-size:10px;font-weight:600">EXEC</span>'
      : '';
    var star = r.reliable
      ? '<span title="Reliable group" style="color:#fbbf24;font-size:13px">&#9733;</span>'
      : '<span style="color:#334155">&#8212;</span>';
    var lowNote = r.low_conv ? '<span style="color:#475569;font-size:10px"> Low conv</span>' : '';
    var dot = '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:'
      + (partyColor[r.party] || '#64748b') + ';margin-right:5px;flex-shrink:0"></span>';
    return '<tr ' + rowBg + ' style="' + dim + '">'
      + '<td class="px-4 py-2.5 font-mono text-xs" style="color:#94a3b8;white-space:nowrap">' + esc(r.date) + '</td>'
      + '<td class="px-4 py-2.5 font-mono text-xs" style="color:#64748b;white-space:nowrap">' + esc(r.tx_date) + '</td>'
      + '<td class="px-4 py-2.5" style="white-space:nowrap"><span style="display:inline-flex;align-items:center">' + dot + '<span style="color:#cbd5e1">' + esc(r.name) + '</span></span>' + (isExec && r.role ? '<div class="text-xs" style="color:#64748b">' + esc(r.role) + '</div>' : '') + '</td>'
      + '<td class="px-4 py-2.5 font-mono font-bold" style="color:#f1f5f9">' + esc(r.ticker) + optBadge + execBadge + '</td>'
      + '<td class="px-4 py-2.5">' + txnBadge + '</td>'
      + '<td class="px-4 py-2.5 text-xs" style="color:#94a3b8;white-space:nowrap">' + esc(r.range) + lowNote + '</td>'
      + '<td class="px-4 py-2.5 text-center">' + star + '</td>'
      + '</tr>';
  }).join('');
  var totalPages = Math.ceil(_currentRows.length / PAGE_SIZE);
  document.getElementById('pageStart').textContent = _currentRows.length ? start + 1 : 0;
  document.getElementById('pageEnd').textContent   = end;
  document.getElementById('pageTotal').textContent = _currentRows.length;
  document.getElementById('pageLabel').textContent = 'Page ' + (_currentPage + 1) + ' of ' + (totalPages || 1);
  document.getElementById('pagePrev').disabled = _currentPage === 0;
  document.getElementById('pageNext').disabled = _currentPage >= totalPages - 1;
  document.getElementById('pagePrev').style.opacity = _currentPage === 0 ? '0.35' : '1';
  document.getElementById('pageNext').style.opacity = _currentPage >= totalPages - 1 ? '0.35' : '1';
}

function changePage(dir) {
  var totalPages = Math.ceil(_currentRows.length / PAGE_SIZE);
  _currentPage = Math.max(0, Math.min(_currentPage + dir, totalPages - 1));
  renderPage();
  document.getElementById('filingsTable').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function filterFilings(mode) {
  document.querySelectorAll('.filing-filter').forEach(function(b) { b.classList.remove('active-filter'); });
  document.querySelector('[data-filter="' + mode + '"]').classList.add('active-filter');
  var rows = FILINGS;
  if (mode === 'purchase') rows = rows.filter(function(r) { return r.txn === 'Purchase'; });
  if (mode === 'sale')     rows = rows.filter(function(r) { return r.txn === 'Sale'; });
  if (mode === 'options')  rows = rows.filter(function(r) { return r.type === 'OP'; });
  if (mode === 'executive')rows = rows.filter(function(r) { return r.source === 'Executive' || r.type === 'EX'; });
  if (mode === 'reliable') rows = rows.filter(function(r) { return r.reliable; });
  if (mode === 'signals')  rows = rows.filter(function(r) { return r.reliable && r.txn === 'Purchase'; });
  if (mode === 'hcsignals')rows = rows.filter(function(r) { return r.hc && r.txn === 'Purchase'; });
  renderFilings(rows);
}

renderFilings(FILINGS);

// Portfolio snapshot
(function() {
  var tbody = document.getElementById('livePositionsBody');
  if (!tbody) return;
  var portfolio = typeof PORTFOLIO !== 'undefined' ? PORTFOLIO : {};
  var positions = Array.isArray(portfolio.positions) ? portfolio.positions : [];
  var count = document.getElementById('livePositionsCount');
  var asOf = portfolio.as_of ? ' · ' + portfolio.as_of : '';
  if (count) count.textContent = positions.length + (positions.length === 1 ? ' position' : ' positions') + asOf;

  var totalPl = Number(portfolio.total_pl || 0);
  var totalPlText = signedMoney(totalPl) + ' (' + signedPct(Number(portfolio.total_pl_pct || 0)) + ')';
  var totalPlColor = totalPl >= 0 ? '#34d399' : '#f87171';
  var fields = [
    ['portfolioEquity', money(portfolio.equity)],
    ['portfolioTotalPl', totalPlText, totalPlColor],
    ['portfolioCash', money(portfolio.cash)],
    ['portfolioInvested', money(portfolio.market_value)]
  ];
  fields.forEach(function(f) {
    var el = document.getElementById(f[0]);
    if (!el) return;
    el.textContent = f[1];
    if (f[2]) el.style.color = f[2];
  });

  if (!positions.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-5 text-center" style="color:#64748b">No open paper positions available.</td></tr>';
    return;
  }
  tbody.innerHTML = positions.map(function(p, i) {
    var rowBg = i % 2 === 0 ? '' : 'style="background:#0f172a40"';
    var role = p.role === 'parking' ? 'SPY parking' : 'Signal';
    var pl = Number(p.unrealized_pl || 0);
    var plColor = pl >= 0 ? '#34d399' : '#f87171';
    return '<tr ' + rowBg + '>'
      + '<td class="px-4 py-2.5 font-mono font-bold" style="color:#f1f5f9">' + esc(p.ticker) + '</td>'
      + '<td class="px-4 py-2.5" style="color:#cbd5e1">' + esc(role) + '</td>'
      + '<td class="px-4 py-2.5 text-right font-mono" style="color:#cbd5e1">' + Number(p.qty || 0).toLocaleString() + '</td>'
      + '<td class="px-4 py-2.5 text-right font-mono" style="color:#cbd5e1">$' + Number(p.avg_entry || 0).toFixed(2) + '</td>'
      + '<td class="px-4 py-2.5 text-right font-mono" style="color:#cbd5e1">$' + Number(p.current_price || 0).toFixed(2) + '</td>'
      + '<td class="px-4 py-2.5 text-right font-mono" style="color:#cbd5e1">' + money(p.market_value) + '</td>'
      + '<td class="px-4 py-2.5 text-right font-mono font-semibold" style="color:' + plColor + '">' + signedMoney(pl) + ' <span style="font-size:11px">(' + signedPct(Number(p.unrealized_pct || 0)) + ')</span></td>'
      + '</tr>';
  }).join('');
})();

// ── Charts ────────────────────────────────────────────────────────────────────
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#1e293b';

var scaleOpts = {
  x: { grid: { color: '#1e293b' }, border: { color: '#334155' } },
  y: { grid: { color: '#1e293b' }, border: { color: '#334155' }, ticks: { callback: function(v) { return '+' + v + '%'; } } }
};

// Hold period chart
new Chart(document.getElementById('holdChart'), {
  type: 'bar',
  data: {
    labels: SENSITIVITY.map(function(s) { return s.hold + 'd'; }),
    datasets: [
      { label: 'Congress (reliable group)', data: SENSITIVITY.map(function(s) { return s.avg_ret; }), backgroundColor: '#10b981', borderRadius: 4, borderSkipped: false },
      { label: 'SPY (same window)',          data: SENSITIVITY.map(function(s) { return s.spy; }),     backgroundColor: '#334155', borderRadius: 4, borderSkipped: false }
    ]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } },
      tooltip: { callbacks: { label: function(ctx) { return ' ' + ctx.dataset.label + ': +' + ctx.raw + '%'; } } }
    },
    scales: scaleOpts
  }
});

// Top performers chart
var politicians = POLITICIANS.slice().sort(function(a, b) { return b.excess - a.excess; });
new Chart(document.getElementById('politiciansChart'), {
  type: 'bar',
  data: {
    labels: politicians.map(function(p) { return p.name; }),
    datasets: [{
      label: 'Avg Excess Return (90d)',
      data: politicians.map(function(p) { return p.excess; }),
      backgroundColor: politicians.map(function(p) {
        return p.trades >= 80 ? '#10b981' : p.trades >= 30 ? '#34d399' : '#6ee7b7';
      }),
      borderRadius: 4, borderSkipped: false
    }]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: function(ctx) {
        return [' Excess: +' + politicians[ctx.dataIndex].excess + '%', ' Trades: ' + politicians[ctx.dataIndex].trades];
      }}}
    },
    scales: Object.assign({}, scaleOpts, {
      x: Object.assign({}, scaleOpts.x, { ticks: { maxRotation: 40, minRotation: 30, font: { size: 11 } } })
    })
  }
});

// Strategy 2 chart
(function() {
  if (typeof STRATEGY2 === 'undefined' || !STRATEGY2.length) return;
  new Chart(document.getElementById('strategy2Chart'), {
    type: 'bar',
    data: {
      labels: STRATEGY2.map(function(r) { return '+' + r.hold_after_sell + 'd'; }),
      datasets: [
        { label: 'Congress (Strategy 2)', data: STRATEGY2.map(function(r) { return r.avg_ret; }), backgroundColor: '#f59e0b', borderRadius: 4, borderSkipped: false },
        { label: 'SPY (same window)',      data: STRATEGY2.map(function(r) { return r.spy; }),     backgroundColor: '#334155', borderRadius: 4, borderSkipped: false }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } },
        tooltip: { callbacks: {
          label: function(ctx) { return ' ' + ctx.dataset.label + ': +' + ctx.raw + '%'; },
          afterBody: function(items) { return '  Excess: +' + STRATEGY2[items[0].dataIndex].excess + '%'; }
        }}
      },
      scales: scaleOpts
    }
  });
})();

// Options chart
new Chart(document.getElementById('optionsChart'), {
  type: 'bar',
  data: {
    labels: ['30d', '60d', '90d'],
    datasets: [
      { label: 'Options signal (buy underlying)', data: [3.8, 0.9, 0.8], backgroundColor: '#818cf8', borderRadius: 4, borderSkipped: false },
      { label: 'Stock signal (all-trades group)', data: [1.1, 1.8, 2.3], backgroundColor: '#334155', borderRadius: 4, borderSkipped: false }
    ]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } },
      tooltip: { callbacks: { label: function(ctx) { return ' ' + ctx.dataset.label + ': +' + ctx.raw + '%'; } } }
    },
    scales: scaleOpts
  }
});
