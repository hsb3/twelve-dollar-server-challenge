/**
 * Sudden surge and recovery: the load.js user at a baseline, a jump to PEAK in a few seconds, then back.
 *
 * Env: BASE (500), PEAK (VUS, default 5000), HOLD (60s), JUMP (10s).
 */
export { default } from '../load.js';

const BASE = Number(__ENV.BASE || 500), PEAK = Number(__ENV.PEAK || __ENV.VUS || 5000);
const HOLD = __ENV.HOLD || '60s', JUMP = __ENV.JUMP || '10s';

export const options = {
  scenarios: {
    users: {
      executor: 'ramping-vus',
      stages: [
        { duration: '30s', target: BASE }, { duration: HOLD, target: BASE },
        { duration: JUMP, target: PEAK }, { duration: HOLD, target: PEAK },
        { duration: JUMP, target: BASE }, { duration: HOLD, target: BASE },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: { http_req_duration: ['p(95)<500', 'p(99)<1000'], http_req_failed: ['rate<0.01'] },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};
