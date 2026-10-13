/**
 * Open model: requests arrive at RATE per second whether or not the server keeps up, so overload shows
 * up as queueing and dropped_iterations instead of the users slowing down (as they do in load.js).
 * One request per iteration, picked by MIX. The default MIX matches load.js's per-user request ratio.
 * Post ids are random across the whole table, so reads are colder than load.js's feed-driven reads.
 *
 * Env: RATE (requests/s, 500), RAMP_UP (60s), DURATION (5m), MIX (feed:46,post:46,like:7,create:1),
 *      MAX_VUS (5000).
 */
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:3000';
const RATE = Number(__ENV.RATE || 500);
const POSTS = 500000;
const tokens = new SharedArray('tokens', () => JSON.parse(open(__ENV.TOKENS || '../../seed/tokens.json')));

const mix = (__ENV.MIX || 'feed:46,post:46,like:7,create:1').split(',').map((kv) => kv.split(':'));
const total = mix.reduce((s, [, w]) => s + Number(w), 0);

export const options = {
  scenarios: {
    requests: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: Math.min(RATE, 1000),
      maxVUs: Number(__ENV.MAX_VUS || 5000),
      stages: [
        { duration: __ENV.RAMP_UP || '60s', target: RATE },
        { duration: __ENV.DURATION || '5m', target: RATE },
      ],
    },
  },
  thresholds: { http_req_duration: ['p(95)<500', 'p(99)<1000'], http_req_failed: ['rate<0.01'] },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};

function pick() {
  let r = Math.random() * total;
  for (const [name, w] of mix) if ((r -= Number(w)) < 0) return name;
  return mix[mix.length - 1][0];
}

export default function () {
  const user = tokens[Math.floor(Math.random() * tokens.length)];
  const auth = { headers: { Authorization: `Bearer ${user.token}`, 'Content-Type': 'application/json' } };
  const id = 1 + Math.floor(Math.random() * POSTS);
  switch (pick()) {
    case 'feed':
      check(http.get(`${BASE_URL}/feed`, { tags: { name: 'GET /feed' } }), { 'feed 200': (r) => r.status === 200 });
      break;
    case 'post':
      check(http.get(`${BASE_URL}/posts/${id}`, { tags: { name: 'GET /posts/:id' } }), { 'post 200': (r) => r.status === 200 });
      break;
    case 'like':
      check(http.post(`${BASE_URL}/posts/${id}/like`, null, { ...auth, tags: { name: 'POST /posts/:id/like' } }),
        { 'like 200/201': (r) => r.status === 200 || r.status === 201 });
      break;
    case 'create': {
      const body = JSON.stringify({ body: `${user.username} says hi at ${new Date().toISOString()}` });
      check(http.post(`${BASE_URL}/posts`, body, { ...auth, tags: { name: 'POST /posts' } }), { 'create 201': (r) => r.status === 201 });
      break;
    }
    default:
      throw new Error(`unknown MIX entry: ${__ENV.MIX}`);
  }
}
