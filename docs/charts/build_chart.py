"""Build docs/charts/score-by-language.html: an interactive report over upstream's leaderboard.

Run: python3 docs/charts/build_chart.py   (stdlib only; reads LEADERBOARD.md)
Python only embeds the rows; the page computes every statistic itself, so the pickers can regroup.
"""
import json
from pathlib import Path

from leaderboard_data import LANGS, STRATEGIES, rows

OUT = Path(__file__).with_name("score-by-language.html")


def build():
    rs = rows()
    data = {"rows": rs, "langs": [l for l, _ in LANGS], "strategies": STRATEGIES,
            "asOf": max(r["scored"] for r in rs)}
    # "</" would end the <script> block if a description ever contained it.
    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
    return OUT


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>$12 server challenge: what drives the score</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
.viz-root { --surface-1:#fcfcfb; --surface-2:#f3f2ee; --text-primary:#1d1d1b; --text-secondary:#52514e; --grid:#e1e0d9;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --box:#efeee9; --good:#0ca30c; --critical:#d03b3b; }
@media (prefers-color-scheme: dark) { .viz-root { --surface-1:#1a1a19; --surface-2:#232321; --text-primary:#f0efec;
  --text-secondary:#c3c2b7; --grid:#33332f; --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --box:#2a2a27; } }
body { margin:0; }
.viz-root { background:var(--surface-1); color:var(--text-primary); font:14px/1.45 system-ui, sans-serif; padding:24px 32px; }
.wrap { max-width:1180px; margin:0 auto; }
h1 { font-size:22px; margin:0 0 2px; } h2 { font-size:15px; margin:0 0 8px; }
p { margin:4px 0 12px; } .muted, .sub { color:var(--text-secondary); }
.controls { display:flex; flex-wrap:wrap; gap:12px 20px; align-items:end; padding:12px 16px; margin:16px 0;
  background:var(--surface-2); border-radius:8px; }
.controls label { display:flex; flex-direction:column; gap:3px; font-size:12px; color:var(--text-secondary); }
.controls select { font:inherit; padding:4px 8px; color:var(--text-primary); background:var(--surface-1);
  border:1px solid var(--grid); border-radius:6px; }
.controls fieldset { border:0; margin:0; padding:0; display:flex; gap:12px; align-items:center; }
.controls legend { font-size:12px; color:var(--text-secondary); padding:0; margin-bottom:3px; }
.controls fieldset label { flex-direction:row; align-items:center; font-size:14px; color:var(--text-primary); }
.main { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(280px,1fr); gap:24px; align-items:start; }
@media (max-width:900px) { .main { grid-template-columns:1fr; } }
.legend { display:flex; flex-wrap:wrap; gap:6px 18px; margin:0 0 4px; color:var(--text-secondary); }
.legend span { display:flex; gap:6px; align-items:center; }
svg { display:block; width:100%; height:auto; }
svg text { fill:var(--text-secondary); font-size:12px; } svg .label { fill:var(--text-primary); font-size:14px; font-weight:600; }
.grid { stroke:var(--grid); } .cap { stroke:var(--text-secondary); stroke-dasharray:4 4; }
.box { fill:var(--box); } .whisker { stroke:var(--text-secondary); stroke-width:1; }
.median { stroke:var(--text-primary); stroke-width:2; } .mean { fill:var(--text-primary); }
.dot { stroke:var(--surface-1); stroke-width:2; cursor:pointer; } .dot:hover, .dot:focus { stroke:var(--text-primary); outline:none; }
.c1 { fill:var(--s1); --c:var(--s1); } .c2 { fill:var(--s2); --c:var(--s2); } .c3 { fill:var(--s3); --c:var(--s3); } .c4 { fill:var(--s4); --c:var(--s4); }
.dot.nginx { fill:var(--surface-1); stroke:var(--c); }
.side { background:var(--surface-2); border-radius:8px; padding:16px; }
.tile { display:grid; grid-template-columns:112px 1fr; gap:12px; align-items:center; padding:8px 0; border-bottom:1px solid var(--grid); }
.tile b { font-size:22px; white-space:nowrap; padding-left:8px; border-left:4px solid var(--grid); }
.tile.good b { border-color:var(--good); } .tile.bad b { border-color:var(--critical); }
.tile small { display:block; font-size:11px; font-weight:400; color:var(--text-secondary); }
.side ul { margin:12px 0 0; padding-left:18px; } .side li { margin:6px 0; }
section { border-top:2px solid var(--grid); margin-top:24px; padding-top:16px; }
.tables { display:flex; flex-wrap:wrap; gap:8px 40px; }
table { border-collapse:collapse; margin:4px 0 12px; font-variant-numeric:tabular-nums; }
caption { text-align:left; color:var(--text-secondary); padding-bottom:4px; }
td, th { padding:3px 10px; text-align:right; border-bottom:1px solid var(--grid); white-space:nowrap; }
td:first-child, th:first-child, td.l, th.l { text-align:left; } th.on, td.on { background:var(--surface-2); }
.scroll { max-height:340px; overflow:auto; border:1px solid var(--grid); border-radius:6px; }
.scroll table { margin:0; width:100%; } .scroll th { position:sticky; top:0; background:var(--surface-1); }
.scroll th.on { background:var(--surface-2); } .scroll td.l { white-space:normal; }
.method { font-size:13px; color:var(--text-secondary); } .method li { margin:3px 0; }
#tip { position:fixed; pointer-events:none; background:var(--surface-1); color:var(--text-primary); border:1px solid var(--grid);
  border-radius:6px; padding:6px 10px; box-shadow:0 2px 8px #0003; display:none; max-width:320px; z-index:2; }
</style></head>
<body><div class="viz-root"><div class="wrap">
<h1>$12 server challenge: what drives the score</h1>
<p class="sub" id="sub"></p>

<div class="controls">
 <label>Category (rows)<select id="cat"></select></label>
 <label>Labels (dot colour)<select id="col"></select></label>
 <label>Metric<select id="met"></select></label>
 <fieldset><legend>Statistics</legend>
  <label><input type="checkbox" id="st-box" checked> Quartile box</label>
  <label><input type="checkbox" id="st-median" checked> Median</label>
  <label><input type="checkbox" id="st-mean" checked> Mean</label>
  <label><input type="checkbox" id="st-range" checked> Min to max</label>
 </fieldset>
</div>

<div class="main">
 <div><div class="legend" id="legend"></div><div id="chart"></div></div>
 <aside class="side"><h2>Observations</h2><div id="tiles"></div><ul id="notes"></ul></aside>
</div>

<section><h2>Data</h2>
 <div class="tables" id="tables"></div>
 <div class="scroll" id="entries"></div>
</section>

<section class="method"><h2>Method and provenance</h2><ul id="method"></ul></section>
<div id="tip"></div>
</div></div>
<script>
const DATA = __DATA__;
const METRICS = {
  users: {label: 'Users held for 5 minutes', short: 'Users held', better: 'higher'},
  reqs:  {label: 'Requests per second at that load', short: 'req/s', better: 'higher'},
  us:    {label: 'Server CPU per request (µs)', short: 'µs/req', better: 'lower'},
  cpu:   {label: 'Server CPU at that load (%)', short: 'CPU %', better: null},
  ram:   {label: 'Server memory at that load (MB)', short: 'RAM MB', better: 'lower'},
  p95:   {label: 'p95 latency at that load (ms)', short: 'p95 ms', better: 'lower'},
};
const DIMS = {
  lang:     {label: 'Language', values: DATA.langs},
  strategy: {label: 'Strategy', values: DATA.strategies},
  nginx:    {label: 'Behind Nginx', values: ['Direct', 'Behind Nginx']},
};
// One note per metric, shown under the tiles. Users held is the score, so it carries the findings.
const NOTES = {
  users: ['With a framework, all four languages land within 1.4x of each other (medians 50k to 71k).',
          'Hand-rolled io_uring is worth 3-4x in the same language: Rust Axum 71k against Rust io_uring 267k (median).',
          'Breaking the 71k wall needs io_uring direct descriptors or retiring idle connections.',
          'No TypeScript/JS entry has tried io_uring, so its ceiling is unknown, not low.'],
  reqs:  ['Requests per second tracks users held: each simulated user sends about one request every 10 seconds.'],
  us:    ['Measured at each entry\'s own passing load, so the loads differ between entries.',
          'Cost per request rises with the number of open connections, so compare entries at similar users held.'],
  cpu:   ['An entry that stops well below 100% CPU was stopped by something else, usually the open-file wall at 71k users.'],
  ram:   ['Memory grows with the number of open connections, so higher scorers use more. Compare entries at similar users held.'],
  p95:   ['Every scored run is under the 500 ms limit by definition. This shows how much room the entry had left.'],
};
const FD_CAP = 71000;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const dimOf = (r, d) => d === 'nginx' ? DIMS.nginx.values[+r.nginx] : r[d];
const fmt = v => v >= 10000 ? Math.round(v / 1000) + 'k' : v >= 1000 ? (v / 1000).toFixed(1) + 'k' : String(Math.round(v));
const mean = xs => xs.reduce((a, b) => a + b, 0) / xs.length;

function stats(xs) {  // quartiles by linear interpolation, the same as Python's "inclusive" method
  const s = [...xs].sort((a, b) => a - b);
  const q = p => { const i = (s.length - 1) * p, lo = Math.floor(i); return s[lo] + (s[Math.ceil(i)] - s[lo]) * (i - lo); };
  return {n: s.length, min: s[0], q1: q(.25), median: q(.5), mean: mean(s), q3: q(.75), max: s[s.length - 1]};
}
function eta2(rows, dim, m) {  // one-way ANOVA: share of the variance that sits between the groups
  const g = mean(rows.map(r => r[m])), groups = {};
  for (const r of rows) (groups[dimOf(r, dim)] ??= []).push(r[m]);
  const between = Object.values(groups).reduce((a, xs) => a + xs.length * (mean(xs) - g) ** 2, 0);
  return between / rows.reduce((a, r) => a + (r[m] - g) ** 2, 0);
}
function niceMax(v) {  // axis end and tick step on a 1/2/5 grid
  const raw = v / 8, p = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 5, 10].find(k => k * p >= raw) * p;
  return {step, max: Math.ceil(v / step) * step};
}
function jitter(name) {  // stable per entry, so a dot keeps its height when the pickers change
  let h = 7; for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return (h % 1000) / 1000 * 36 - 18;
}

function render() {
  const cat = $('cat').value, col = $('col').value, m = $('met').value, M = METRICS[m];
  const show = k => $('st-' + k).checked;
  const rows = DATA.rows, groupOf = v => rows.filter(r => dimOf(r, cat) === v);
  const sign = M.better === 'lower' ? 1 : -1;  // best row first
  const cats = DIMS[cat].values.map(v => ({v, s: stats(groupOf(v).map(r => r[m]))})).sort((a, b) => sign * (a.s.median - b.s.median));
  const cls = r => 'c' + (DIMS[col].values.indexOf(dimOf(r, col)) + 1);

  // chart
  const W = 700, LEFT = 118, RIGHT = 20, TOP = 30, ROW = 96, H = TOP + ROW * cats.length + 58;
  const ax = niceMax(Math.max(...rows.map(r => r[m]))), x = v => LEFT + v / ax.max * (W - LEFT - RIGHT);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(M.label)} per entry, by ${DIMS[cat].label.toLowerCase()}">`;
  for (let v = 0; v <= ax.max + 1e-9; v += ax.step)
    svg += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${TOP}" y2="${H - 52}"/><text x="${x(v)}" y="${H - 34}" text-anchor="middle">${fmt(v)}</text>`;
  svg += `<text x="${(LEFT + W - RIGHT) / 2}" y="${H - 10}" text-anchor="middle">${esc(M.label)}${M.better ? ` (${M.better} is better)` : ''} →</text>`;
  if (m === 'users')
    svg += `<line class="cap" x1="${x(FD_CAP)}" x2="${x(FD_CAP)}" y1="${TOP - 10}" y2="${H - 52}"/><text x="${x(FD_CAP) + 4}" y="${TOP - 14}">65,535 open-file limit ≈ 71k users</text>`;
  cats.forEach(({v, s}, i) => {
    const mid = TOP + ROW * i + ROW / 2;
    svg += `<text class="label" x="${LEFT - 12}" y="${mid}" text-anchor="end">${esc(v.replace('Hand-rolled ', '').replace(' or runtime server', ''))}</text>`
         + `<text x="${LEFT - 12}" y="${mid + 16}" text-anchor="end">n = ${s.n}</text>`;
    if (show('range')) svg += `<line class="whisker" x1="${x(s.min)}" x2="${x(s.max)}" y1="${mid}" y2="${mid}"/>`;
    if (show('box')) svg += `<rect class="box" x="${x(s.q1)}" y="${mid - 26}" width="${x(s.q3) - x(s.q1)}" height="52" rx="4"/>`;
    if (show('median')) svg += `<line class="median" x1="${x(s.median)}" x2="${x(s.median)}" y1="${mid - 26}" y2="${mid + 26}"/>`;
    if (show('mean')) svg += `<path class="mean" d="M${x(s.mean)},${mid - 28} l6,-8 h-12 z"/>`;
    for (const r of groupOf(v))
      svg += `<circle class="dot ${cls(r)}${r.nginx ? ' nginx' : ''}" tabindex="0" cx="${x(r[m])}" cy="${(mid + jitter(r.name)).toFixed(1)}" r="5" data-i="${rows.indexOf(r)}"/>`;
  });
  $('chart').innerHTML = svg + '</svg>';
  $('legend').innerHTML = DIMS[col].values.map((v, i) =>
    `<span><svg style="width:12px" viewBox="0 0 12 12"><circle class="dot c${i + 1}" cx="6" cy="6" r="5"/></svg>${esc(v)}</span>`).join('')
    + '<span>▌median</span><span>▼ mean</span><span>○ behind Nginx</span>';

  // observation tiles
  const e = {strategy: eta2(rows, 'strategy', m), lang: eta2(rows, 'lang', m)};
  const top = e.strategy >= e.lang ? 'strategy' : 'lang';
  const pct = v => Math.round(v * 100) + '%', what = M.short.toLowerCase();
  const best = cats[0], worst = cats[cats.length - 1], ratio = Math.max(best.s.median, worst.s.median) / Math.min(best.s.median, worst.s.median);
  const tiles = ['strategy', 'lang'].map(d => [d === top ? 'good' : '', pct(e[d]),
    `of the spread in ${what} is explained by ${DIMS[d].label.toLowerCase()}${d === top ? ': the bigger driver' : ''}`, d === top ? '✓ main driver' : '']);
  tiles.push(['', ratio.toFixed(1) + 'x', `between the best and worst median: ${best.v} ${fmt(best.s.median)}, ${worst.v} ${fmt(worst.s.median)}`, '']);
  if (m === 'users') {
    const stuck = rows.filter(r => r.users === FD_CAP).length;
    tiles.push(['bad', stuck + ' of ' + rows.length, 'entries stop at exactly 71k users: the open-file limit, not their language\'s limit', '! shared wall']);
  } else {
    const b = [...rows].sort((a, c) => sign * (a[m] - c[m]))[0];
    tiles.push(['', fmt(b[m]), `${M.better === 'lower' ? 'lowest' : 'highest'} ${what}: ${b.name}`, '']);
  }
  $('tiles').innerHTML = tiles.map(([c, big, text, tag]) =>
    `<div class="tile ${c}"><b>${esc(big)}${tag ? `<small>${esc(tag)}</small>` : ''}</b><span>${esc(text)}</span></div>`).join('');
  $('notes').innerHTML = NOTES[m].map(t => `<li>${esc(t)}</li>`).join('');

  // tables
  const keys = ['n', 'min', 'q1', 'median', 'mean', 'q3', 'max'], cell = (k, v) => k === 'n' ? v : fmt(v);
  let t = `<table><caption>${esc(M.short)}, by ${DIMS[cat].label.toLowerCase()}</caption><tr><th></th>${keys.map(k => `<th>${k === 'q1' ? 'Q1' : k === 'q3' ? 'Q3' : k}</th>`).join('')}</tr>`
    + cats.map(({v, s}) => `<tr><td>${esc(v)}</td>${keys.map(k => `<td>${cell(k, s[k])}</td>`).join('')}</tr>`).join('') + '</table>';
  if (col !== cat) {
    t += `<table><caption>Median ${esc(M.short.toLowerCase())} by ${DIMS[cat].label.toLowerCase()} and ${DIMS[col].label.toLowerCase()} (number of entries)</caption><tr><th></th>${DIMS[col].values.map(v => `<th>${esc(v)}</th>`).join('')}</tr>`
      + cats.map(({v}) => `<tr><td>${esc(v)}</td>` + DIMS[col].values.map(c => {
          const xs = groupOf(v).filter(r => dimOf(r, col) === c).map(r => r[m]);
          return `<td>${xs.length ? `${fmt(stats(xs).median)} <span class="muted">(${xs.length})</span>` : '–'}</td>`;
        }).join('') + '</tr>').join('') + '</table>';
  }
  $('tables').innerHTML = t;
  const mk = Object.keys(METRICS);
  $('entries').innerHTML = `<table><tr><th>Entry</th><th class="l">Language</th><th class="l">Strategy</th><th class="l">Description</th>`
    + mk.map(k => `<th class="${k === m ? 'on' : ''}">${esc(METRICS[k].short)}</th>`).join('') + '</tr>'
    + [...rows].sort((a, b) => sign * (a[m] - b[m])).map(r => `<tr><td>${esc(r.name)}</td><td class="l">${esc(r.lang)}</td><td class="l">${esc(r.strategy)}</td><td class="l">${esc(r.desc)}</td>`
      + mk.map(k => `<td class="${k === m ? 'on' : ''}">${Math.round(r[k]).toLocaleString('en-US')}</td>`).join('') + '</tr>').join('') + '</table>';
}

// tooltip: hover or keyboard focus on a dot
const tip = $('tip');
function showTip(d, px, py) {
  const r = DATA.rows[d.dataset.i], m = $('met').value;
  tip.innerHTML = `<b>${esc(r.name)}</b><br>${esc(METRICS[m].short)}: ${Math.round(r[m]).toLocaleString('en-US')}`
    + (m === 'users' ? '' : `<br>Users held: ${r.users.toLocaleString('en-US')}`)
    + `<br><span class="muted">${esc(r.desc)}<br>${esc(r.strategy)}</span>`;
  tip.style.display = 'block';
  tip.style.left = Math.min(px + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (py + 14) + 'px';
}
$('chart').addEventListener('mousemove', e => e.target.dataset.i ? showTip(e.target, e.clientX, e.clientY) : tip.style.display = 'none');
$('chart').addEventListener('mouseleave', () => tip.style.display = 'none');
$('chart').addEventListener('focusin', e => { if (e.target.dataset.i) { const b = e.target.getBoundingClientRect(); showTip(e.target, b.right, b.bottom); } });
$('chart').addEventListener('focusout', () => tip.style.display = 'none');

const opts = (o, keys) => keys.map(k => `<option value="${k}">${esc(o[k].label)}</option>`).join('');
$('cat').innerHTML = opts(DIMS, ['lang', 'strategy']);
$('col').innerHTML = opts(DIMS, ['strategy', 'lang', 'nginx']);
$('met').innerHTML = opts(METRICS, Object.keys(METRICS));
document.querySelector('.controls').addEventListener('change', render);
$('sub').textContent = `Each dot is one of the ${DATA.rows.length} entries in Rust, Go, Python and TypeScript/JS on upstream's leaderboard. Pick how to group, colour and measure them.`;
$('method').innerHTML = [
  `Source: upstream's LEADERBOARD.md, entries scored up to ${DATA.asOf}. Rebuild with <code>python3 docs/charts/build_chart.py</code>.`,
  'Machine: 1 vCPU, 2 GB RAM, with the load generated from separate machines. Every entry runs the same load test.',
  'Score: the most simulated users held for 5 minutes with p95 under 500 ms, p99 under 1 s and under 1% errors. The other metrics are measured during that passing run.',
  'Scope: Rust, Go, Python (CPython and PyPy) and TypeScript/JS (Node, Bun and Deno). Other languages on the leaderboard are left out.',
  'Strategy comes from each entry\'s description: it names io_uring, or epoll, or neither (a framework or the runtime\'s own server).',
  '"Spread explained" is one-way ANOVA η²: the share of the variance that sits between the groups. Language and strategy overlap, so the two shares do not add up to 100%.',
  'Re-running the same code moves a score by 5-15%, so ignore gaps under about 10k users.',
].map(t => `<li>${t}</li>`).join('');
render();
</script>
</body></html>
"""

if __name__ == "__main__":
    print(build())
