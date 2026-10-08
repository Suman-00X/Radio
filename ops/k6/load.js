// k6 load test against a running radreport, safe for Render's free plan.
//
// Order: wake the instance and wait for /ready (setup; a sleeping free instance takes 30-60 s) ->
// sign in once with a read-only demo account -> run a read-only mix of lab routes and probes ->
// fail the run on error rate or p95 latency (thresholds).
//
//   k6 run -e BASE_URL=https://radreport-web.onrender.com -e LAB=sunrise \
//          -e EMAIL=<demo email> -e PASSWORD=<demo password> ops/k6/load.js
//
// Rate limits (access_policy.xml) cap what one machine can send: lab reads are 300/min per signed-in
// user and every VU shares the one token, probes are 1200/min per IP, sign-in is 5/min per IP.
// The defaults (4 VUs, ~1 s think time) stay under them; more VUs measure the limiter, not the app.
// Without EMAIL/PASSWORD only the probes run.

import http from "k6/http";
import { check, sleep, fail } from "k6";
import { Counter } from "k6/metrics";

const BASE = (__ENV.BASE_URL || "http://127.0.0.1:8078").replace(/\/$/, "");
const VUS = Number(__ENV.VUS || 4);
const DURATION = __ENV.DURATION || "2m";
const WAKE_SECONDS = Number(__ENV.WAKE_SECONDS || 180);

const rateLimited = new Counter("rate_limited");

export const options = {
  setupTimeout: `${WAKE_SECONDS + 30}s`,
  scenarios: {
    lab_reads: {
      executor: "ramping-vus",
      stages: [
        { duration: "20s", target: VUS },
        { duration: DURATION, target: VUS },
        { duration: "10s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{kind:lab}": ["p(95)<1500"],
    "http_req_duration{kind:probe}": ["p(95)<500"],
    rate_limited: ["count<10"],
  },
};

const LAB_MIX = [
  [5, "/review/queue"],
  [3, "/review/queue/stats"],
  [3, "/ingest/recordings?page_size=20"],
  [1, "/review/metrics/usefulness"],
].flatMap(([w, p]) => Array(w).fill(p));

export function setup() {
  const started = Date.now();
  let ready = false;
  while ((Date.now() - started) / 1000 < WAKE_SECONDS) {
    const res = http.get(`${BASE}/ready`, { timeout: "60s", tags: { kind: "wake" } });
    if (res.status === 200) {
      ready = true;
      break;
    }
    sleep(5);
  }
  if (!ready) fail(`${BASE}/ready did not answer 200 within ${WAKE_SECONDS}s`);
  console.log(`awake after ${Math.round((Date.now() - started) / 1000)}s`);

  if (!__ENV.EMAIL || !__ENV.PASSWORD) return { token: null };
  const res = http.post(
    `${BASE}/auth/login`,
    JSON.stringify({ lab: __ENV.LAB || "sunrise", email: __ENV.EMAIL, password: __ENV.PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { kind: "login" } },
  );
  if (res.status !== 200) fail(`sign-in answered ${res.status}: ${res.body}`);
  return { token: res.json("access_token") };
}

export default function (data) {
  let res;
  if (data.token && Math.random() < 0.9) {
    const path = LAB_MIX[Math.floor(Math.random() * LAB_MIX.length)];
    res = http.get(`${BASE}${path}`, {
      headers: { Authorization: `Bearer ${data.token}` },
      tags: { kind: "lab", name: path.split("?")[0] },
    });
  } else {
    res = http.get(`${BASE}/health`, { tags: { kind: "probe", name: "/health" } });
  }
  if (res.status === 429) rateLimited.add(1);
  check(res, { "status 200": (r) => r.status === 200 });
  sleep(0.5 + Math.random());
}
