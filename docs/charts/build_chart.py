"""Build docs/charts/score-by-language.html: users held per entry, by language and strategy.

Run: python3 docs/charts/build_chart.py   (stdlib only; reads LEADERBOARD.md)
"""
import html
import json
import random
from pathlib import Path

from leaderboard_data import LANGS, STRATEGIES, eta_squared, quartiles, rows

OUT = Path(__file__).with_name("score-by-language.html")
W, LEFT, RIGHT, ROW_H, TOP = 960, 120, 24, 96, 28
XMAX = 320_000
FD_CAP = 71_000


def x(v):
    return LEFT + v / XMAX * (W - LEFT - RIGHT)


def build():
    rs = rows()
    langs = sorted({r["lang"] for r in rs}, key=lambda l: -quartiles([r["users"] for r in rs if r["lang"] == l])["median"])
    random.seed(7)  # stable jitter between builds
    h = TOP + ROW_H * len(langs) + 40
    svg = [f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="Users held per entry, by language, coloured by strategy">']
    for v in range(0, XMAX + 1, 50_000):
        svg.append(f'<line class="grid" x1="{x(v)}" x2="{x(v)}" y1="{TOP}" y2="{h - 34}"/>'
                   f'<text class="axis" x="{x(v)}" y="{h - 16}" text-anchor="middle">{v // 1000}k</text>')
    svg.append(f'<line class="cap" x1="{x(FD_CAP)}" x2="{x(FD_CAP)}" y1="{TOP - 10}" y2="{h - 34}"/>'
               f'<text class="axis" x="{x(FD_CAP) + 4}" y="{TOP - 14}">65,535 open-file cap ≈ 71k</text>')
    for i, lang in enumerate(langs):
        mid = TOP + ROW_H * i + ROW_H / 2
        q = quartiles([r["users"] for r in rs if r["lang"] == lang])
        svg.append(f'<text class="label" x="{LEFT - 12}" y="{mid + 5}" text-anchor="end">{lang}</text>'
                   f'<line class="whisker" x1="{x(q["min"])}" x2="{x(q["max"])}" y1="{mid}" y2="{mid}"/>'
                   f'<rect class="box" x="{x(q["q1"])}" y="{mid - 26}" width="{x(q["q3"]) - x(q["q1"])}" height="52" rx="4"/>'
                   f'<line class="median" x1="{x(q["median"])}" x2="{x(q["median"])}" y1="{mid - 26}" y2="{mid + 26}"/>'
                   f'<path class="mean" d="M{x(q["mean"])},{mid - 33} l6,-7 h-12 z"/>')
        for r in (r for r in rs if r["lang"] == lang):
            tip = html.escape(json.dumps({"n": r["name"], "d": r["desc"], "u": r["users"], "s": r["strategy"]}))
            cls = f's{STRATEGIES.index(r["strategy"]) + 1}' + (" nginx" if r["nginx"] else "")
            svg.append(f'<circle class="dot {cls}" cx="{x(r["users"])}" cy="{mid + random.uniform(-18, 18):.1f}" r="5" data-tip="{tip}"/>')
    svg.append("</svg>")

    def stat_rows(key, names):
        out = []
        for n in names:
            q = quartiles([r["users"] for r in rs if r[key] == n])
            out.append(f'<tr><td>{n}</td><td>{q["n"]}</td>' + "".join(
                f'<td>{q[k] / 1000:.0f}k</td>' for k in ("min", "q1", "median", "mean", "q3", "max")) + "</tr>")
        return "".join(out)

    cells = []
    for lang in langs:
        tds = []
        for s in STRATEGIES:
            xs = [r["users"] for r in rs if r["lang"] == lang and r["strategy"] == s]
            tds.append(f'<td>{quartiles(xs)["median"] / 1000:.0f}k <span class="muted">(n={len(xs)})</span></td>' if xs else "<td>–</td>")
        cells.append(f"<tr><td>{lang}</td>{''.join(tds)}</tr>")
    for r in rs:
        r["cell"] = r["lang"] + r["strategy"]
    eta_l, eta_s, eta_c = (eta_squared(rs, k) for k in ("lang", "strategy", "cell"))

    legend = "".join(f'<span><svg width="12" height="12"><circle class="dot s{i + 1}" cx="6" cy="6" r="5"/></svg>{s}</span>'
                     for i, s in enumerate(STRATEGIES))
    head = "<tr><th></th><th>n</th><th>min</th><th>Q1</th><th>median</th><th>mean</th><th>Q3</th><th>max</th></tr>"
    OUT.write_text(TEMPLATE.format(
        svg="\n".join(svg), legend=legend, n=len(rs),
        eta_l=f"{eta_l:.0%}", eta_s=f"{eta_s:.0%}", eta_c=f"{eta_c:.0%}",
        lang_table=head + stat_rows("lang", langs), strat_table=head + stat_rows("strategy", STRATEGIES),
        cell_head="<tr><th></th>" + "".join(f"<th>{s}</th>" for s in STRATEGIES) + "</tr>", cells="".join(cells)))
    return OUT


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Users held, by language and strategy</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
.viz-root {{ --surface-1:#fcfcfb; --text-primary:#1d1d1b; --text-secondary:#5f5e58; --grid:#e4e3de;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --box:#efeee9; }}
@media (prefers-color-scheme: dark) {{ .viz-root {{ --surface-1:#1a1a19; --text-primary:#f0efec; --text-secondary:#c3c2b7;
  --grid:#33332f; --s1:#3987e5; --s2:#d95926; --s3:#199e70; --box:#262624; }} }}
body {{ margin:0; }}
.viz-root {{ background:var(--surface-1); color:var(--text-primary); font:14px/1.45 system-ui, sans-serif; padding:24px 32px; max-width:1000px; }}
h1 {{ font-size:20px; margin:0 0 4px; }} p {{ margin:4px 0 12px; color:var(--text-secondary); }}
.legend {{ display:flex; gap:20px; margin:8px 0; color:var(--text-secondary); }} .legend span {{ display:flex; gap:6px; align-items:center; }}
svg text {{ fill:var(--text-secondary); font-size:12px; }} svg .label {{ fill:var(--text-primary); font-size:14px; font-weight:600; }}
.grid {{ stroke:var(--grid); }} .cap {{ stroke:var(--text-secondary); stroke-dasharray:4 4; }}
.box {{ fill:var(--box); }} .whisker {{ stroke:var(--text-secondary); stroke-width:1; }}
.median {{ stroke:var(--text-primary); stroke-width:2; }} .mean {{ fill:var(--text-primary); }}
.dot {{ stroke:var(--surface-1); stroke-width:2; cursor:pointer; }} .dot:hover {{ stroke:var(--text-primary); }}
.s1 {{ fill:var(--s1); }} .s2 {{ fill:var(--s2); }} .s3 {{ fill:var(--s3); }}
.nginx {{ fill:var(--surface-1); stroke:var(--s1); stroke-width:2; }}
.stats {{ display:flex; gap:24px; margin:12px 0; }} .stat b {{ display:block; font-size:24px; }}
table {{ border-collapse:collapse; margin:8px 0 16px; font-variant-numeric:tabular-nums; }}
td, th {{ padding:3px 10px; text-align:right; border-bottom:1px solid var(--grid); }} td:first-child, th:first-child {{ text-align:left; }}
.muted {{ color:var(--text-secondary); }}
#tip {{ position:fixed; pointer-events:none; background:var(--surface-1); color:var(--text-primary); border:1px solid var(--grid);
  border-radius:6px; padding:6px 10px; box-shadow:0 2px 8px #0003; display:none; max-width:320px; }}
</style></head>
<body><div class="viz-root">
<h1>Users held, by language and strategy</h1>
<p>Each dot is one entry on upstream's leaderboard ({n} entries in Rust, Go, Python and TypeScript/JS, which includes Node, Bun and Deno).
Box = quartiles, bar = median, ▼ = mean. Hollow dots run behind Nginx.</p>
<div class="stats">
 <div class="stat"><b>{eta_s}</b>of the spread explained by strategy</div>
 <div class="stat"><b>{eta_l}</b>explained by language</div>
 <div class="stat"><b>{eta_c}</b>by both together</div>
</div>
<div class="legend">{legend}</div>
{svg}
<details open><summary>Median by language and strategy</summary><table>{cell_head}{cells}</table></details>
<details><summary>Table view: by language</summary><table>{lang_table}</table></details>
<details><summary>Table view: by strategy</summary><table>{strat_table}</table></details>
<p>Source: upstream LEADERBOARD.md. "Spread explained" is one-way ANOVA η² on users held. Built by docs/charts/build_chart.py.</p>
<div id="tip"></div>
</div>
<script>
const tip = document.getElementById('tip');
document.querySelectorAll('.dot[data-tip]').forEach(d => {{
  d.addEventListener('mousemove', e => {{
    const t = JSON.parse(d.dataset.tip);
    tip.innerHTML = `<b>${{t.n}}</b><br>${{t.u.toLocaleString()}} users<br><span class="muted">${{t.d}}<br>${{t.s}}</span>`;
    tip.style.display = 'block'; tip.style.left = (e.clientX + 14) + 'px'; tip.style.top = (e.clientY + 14) + 'px';
  }});
  d.addEventListener('mouseleave', () => tip.style.display = 'none');
}});
</script>
</body></html>
"""

if __name__ == "__main__":
    print(build())
