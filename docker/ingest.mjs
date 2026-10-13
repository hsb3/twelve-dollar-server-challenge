// Folds bench runs into results/runs.db (what Grafana reads): one row per run, one row per run-second.
// Re-ingesting a run replaces it, so `node docker/ingest.mjs results/*/` rebuilds the database.
//
//   node docker/ingest.mjs results/<run-id> [...]
import { createReadStream, existsSync, readFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { createGunzip } from 'node:zlib';
import { DatabaseSync } from 'node:sqlite';
import { join, dirname } from 'node:path';

const pct = (sorted, p) => (sorted.length ? sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)] : null);
const round = (x, d = 2) => (x == null ? null : Math.round(x * 10 ** d) / 10 ** d);

async function k6Seconds(file) {
  const secs = new Map();
  const at = (t) => secs.get(t) ?? secs.set(t, { vus: 0, reqs: 0, failed: 0, durations: [], dropped: 0 }).get(t);
  const lines = createInterface({ input: createReadStream(file).pipe(createGunzip()), crlfDelay: Infinity });
  let header = true;
  for await (const line of lines) {
    if (header) { header = false; continue; }
    // The first three columns never contain commas; later ones (error text) can.
    const [metric, ts, value] = line.split(',', 3);
    const s = at(Number(ts)), v = Number(value);
    if (metric === 'http_req_duration') s.durations.push(v);
    else if (metric === 'http_reqs') s.reqs += v;
    else if (metric === 'http_req_failed') s.failed += v;
    else if (metric === 'vus') s.vus = Math.max(s.vus, v);
    else if (metric === 'dropped_iterations') s.dropped += v;
  }
  return secs;
}

async function statsSeconds(file) {
  const secs = new Map();
  if (!existsSync(file)) return secs;
  let prev = null;
  for await (const line of createInterface({ input: createReadStream(file), crlfDelay: Infinity })) {
    if (!line.trim()) continue;
    const s = JSON.parse(line);
    const now = { ns: Date.parse(s.read) * 1e6, cpu: s.cpu_stats.cpu_usage.total_usage };
    if (!s.memory_stats?.usage) break;   // the container stopped
    // Same figure as `docker stats`: usage minus reclaimable page cache.
    const mem = (s.memory_stats.usage - (s.memory_stats.stats?.inactive_file ?? 0)) / 2 ** 20;
    const cpu = prev ? ((now.cpu - prev.cpu) / (now.ns - prev.ns)) * 100 : null;
    secs.set(Math.floor(now.ns / 1e9), { cpu, mem });
    prev = now;
  }
  return secs;
}

async function ingest(db, dir) {
  const meta = JSON.parse(readFileSync(join(dir, 'meta.json'), 'utf8'));
  const k6 = await k6Seconds(join(dir, 'k6.csv.gz'));
  const stats = await statsSeconds(join(dir, 'server-stats.jsonl'));
  if (!k6.size) throw new Error(`${dir}: no k6 samples`);
  const t0 = Math.min(...k6.keys()), tEnd = Math.max(...k6.keys());
  // Keep a few idle seconds before the load; drop the server's shutdown after it.
  for (const sec of stats.keys()) if (sec < t0 - 5 || sec > tEnd) stats.delete(sec);

  const all = [];
  let reqs = 0, failed = 0, peakMem = 0, peakCpu = 0;
  const rows = [];
  for (const sec of [...new Set([...k6.keys(), ...stats.keys()])].sort((a, b) => a - b)) {
    const k = k6.get(sec), st = stats.get(sec);
    const d = k ? k.durations.sort((a, b) => a - b) : [];
    for (const x of d) all.push(x);
    reqs += k?.reqs ?? 0; failed += k?.failed ?? 0;
    peakMem = Math.max(peakMem, st?.mem ?? 0); peakCpu = Math.max(peakCpu, st?.cpu ?? 0);
    rows.push([meta.run_id, sec - t0, k?.vus ?? null, k?.reqs ?? null, k?.reqs ? round((100 * k.failed) / k.reqs) : null,
      round(pct(d, 50)), round(pct(d, 95)), round(pct(d, 99)), round(d.at(-1)), k?.dropped ?? null,
      round(st?.cpu, 1), round(st?.mem, 1)]);
  }
  all.sort((a, b) => a - b);
  const exit = existsSync(join(dir, 'k6-exit')) ? Number(readFileSync(join(dir, 'k6-exit'), 'utf8')) : null;

  db.exec('BEGIN');
  db.prepare('DELETE FROM samples WHERE run_id = ?').run(meta.run_id);
  db.prepare('DELETE FROM runs WHERE run_id = ?').run(meta.run_id);
  db.prepare(`INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
    meta.run_id, meta.started_at, meta.submission, meta.scenario, meta.vus, meta.nginx, meta.cpus, meta.memory,
    meta.platform, meta.env, exit, reqs, round(pct(all, 95)), round(pct(all, 99)), reqs ? round((100 * failed) / reqs, 3) : null,
    round(peakMem, 1), round(peakCpu, 1), meta.command, meta.git_sha, meta.image_id);
  const ins = db.prepare('INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)');
  for (const r of rows) ins.run(...r);
  db.exec('COMMIT');
  console.log(`ingested ${meta.run_id}: ${rows.length} s, ${reqs} requests, p95 ${round(pct(all, 95))} ms, peak ${round(peakMem, 1)} MB`);
}

const dirs = process.argv.slice(2);
if (!dirs.length) { console.error('usage: node docker/ingest.mjs results/<run-id> [...]'); process.exit(2); }
const db = new DatabaseSync(join(dirname(dirs[0].replace(/\/$/, '')), 'runs.db'));
db.exec(`
  CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, started_at TEXT, submission TEXT, scenario TEXT, vus INTEGER,
    nginx INTEGER, cpus TEXT, memory TEXT, platform TEXT, env TEXT, k6_exit INTEGER, reqs INTEGER, p95_ms REAL, p99_ms REAL,
    err_pct REAL, peak_mem_mb REAL, peak_cpu_pct REAL, command TEXT, git_sha TEXT, image_id TEXT);
  CREATE TABLE IF NOT EXISTS samples (run_id TEXT, t INTEGER, vus INTEGER, rps INTEGER, err_pct REAL, p50_ms REAL,
    p95_ms REAL, p99_ms REAL, max_ms REAL, dropped INTEGER, cpu_pct REAL, mem_mb REAL, PRIMARY KEY (run_id, t));`);
let failed = 0;
for (const dir of dirs) {
  if (!existsSync(join(dir, 'meta.json'))) { console.log(`skip ${dir}: no meta.json`); continue; }
  try { await ingest(db, dir); } catch (e) { failed++; console.error(`FAIL ${dir}: ${e.message}`); }
}
process.exit(failed ? 1 : 0);
