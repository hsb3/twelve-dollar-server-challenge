"""Parse LEADERBOARD.md into rows for Rust, Go, Python and TypeScript/JS, tagged by strategy.

Run: python3 docs/charts/leaderboard_data.py  -> prints stats; build_chart.py imports rows().
"""
import re
import statistics
from pathlib import Path

LB = Path(__file__).resolve().parents[2] / "LEADERBOARD.md"
ROW = re.compile(r"^\| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| \*\*([\d,]+)\*\*")
LANGS = [("Rust", r"^Rust\b"), ("Go", r"^Go\b"), ("Python", r"^(Python|PyPy)\b"),
         ("TypeScript/JS", r"^(TypeScript|Node|Bun|Deno|JavaScript)\b")]
STRATEGIES = ["Framework or runtime server", "Hand-rolled epoll", "Hand-rolled io_uring"]


def strategy(desc):
    d = desc.lower()
    if "io_uring" in d:
        return STRATEGIES[2]
    if "epoll" in d and "fib" not in d:  # fib is a framework that happens to name its poller
        return STRATEGIES[1]
    return STRATEGIES[0]


def rows():
    out = []
    for line in LB.read_text().splitlines():
        m = ROW.match(line)
        if not m:
            continue
        _, name, pr, desc, users = (g.strip() for g in m.groups())
        lang = next((l for l, pat in LANGS if re.match(pat, desc)), None)
        if lang:
            out.append({"name": name, "pr": pr, "desc": desc, "lang": lang, "users": int(users.replace(",", "")),
                        "strategy": strategy(desc), "nginx": "behind nginx" in desc.lower()})
    return out


def quartiles(xs):
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) > 1 else [xs[0]] * 3
    return {"n": len(xs), "min": min(xs), "q1": q[0], "median": q[1], "q3": q[2], "max": max(xs),
            "mean": statistics.fmean(xs)}


def eta_squared(rs, key):
    """Share of score variance explained by grouping on `key` (one-way ANOVA eta^2)."""
    ys = [r["users"] for r in rs]
    grand = statistics.fmean(ys)
    total = sum((y - grand) ** 2 for y in ys)
    groups = {}
    for r in rs:
        groups.setdefault(r[key], []).append(r["users"])
    between = sum(len(g) * (statistics.fmean(g) - grand) ** 2 for g in groups.values())
    return between / total


if __name__ == "__main__":
    rs = rows()
    assert len(rs) > 40 and {r["lang"] for r in rs} == {l for l, _ in LANGS}, "parse failed"
    for lang, _ in LANGS:
        print(lang, {k: round(v) for k, v in quartiles([r["users"] for r in rs if r["lang"] == lang]).items()})
    for s in STRATEGIES:
        xs = [r["users"] for r in rs if r["strategy"] == s]
        print(s, {k: round(v) for k, v in quartiles(xs).items()})
    print("eta2 language", round(eta_squared(rs, "lang"), 2), "eta2 strategy", round(eta_squared(rs, "strategy"), 2))
    for r in rs:
        r["ls"] = r["lang"] + "|" + r["strategy"]
    print("eta2 language+strategy cells", round(eta_squared(rs, "ls"), 2))
    for r in sorted(rs, key=lambda r: (r["lang"], r["strategy"])):
        print(f'  {r["lang"]:14} {r["strategy"][:22]:22} {r["users"]:>7} {r["name"]}  [{r["desc"][:50]}]')
