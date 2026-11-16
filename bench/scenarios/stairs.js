/**
 * Capacity curve in one run: the load.js user, stepping up VUs and holding each step.
 * Where p95 bends is roughly the score the doubling search in README.md would find.
 *
 * Env: START (500), STEP (500), STEPS (8), HOLD (60s), RAMP (15s).
 */
export { default } from '../load.js';

const START = Number(__ENV.START || 500), STEP = Number(__ENV.STEP || 500), STEPS = Number(__ENV.STEPS || 8);
const stages = [];
for (let i = 0; i < STEPS; i++) {
  stages.push({ duration: __ENV.RAMP || '15s', target: START + i * STEP });
  stages.push({ duration: __ENV.HOLD || '60s', target: START + i * STEP });
}
stages.push({ duration: '30s', target: 0 });

export const options = {
  scenarios: { users: { executor: 'ramping-vus', stages, gracefulRampDown: '10s' } },
  thresholds: { http_req_duration: ['p(95)<500', 'p(99)<1000'], http_req_failed: ['rate<0.01'] },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};
