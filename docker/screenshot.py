"""Save a full-page PNG of the Grafana dashboard with the given runs overlaid.

Usage (from the shots service): python /screenshot.py <out.png> <minutes> <run_id>...
"""
import sys
import time
import urllib.request
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright

out, minutes, runs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
assert runs, "give at least one run id"
query = urlencode([("var-run", r) for r in runs] + [("from", "0"), ("to", str(minutes * 60_000)), ("kiosk", "true")])
for _ in range(60):  # Grafana may still be starting or installing its plugin
    try:
        if urllib.request.urlopen("http://grafana:3000/api/health", timeout=2).status == 200:
            break
    except OSError:
        pass
    time.sleep(2)
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1600, "height": 1000}, locale="en-US")  # the image's POSIX locale crashes Grafana
    page.goto(f"http://grafana:3000/d/bench-runs/?{query}", wait_until="networkidle")
    page.get_by_text("Server memory").first.wait_for(timeout=60_000)
    page.wait_for_timeout(3000)  # panels finish drawing after the last query returns
    # kiosk mode scrolls inside the page, so grow the viewport to the dashboard's height
    height = page.evaluate("Math.max(...[...document.querySelectorAll('*')].map(e => e.scrollHeight))")
    page.set_viewport_size({"width": 1600, "height": min(height, 6000)})
    page.wait_for_timeout(2000)
    page.screenshot(path=out, full_page=True)
print(out)
