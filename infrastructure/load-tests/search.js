import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const searchErrors = new Rate("tamiltrove_search_errors");
const searchLatency = new Trend("tamiltrove_search_latency", true);
const apiUrl = (__ENV.API_URL || "http://localhost:8000").replace(/\/+$/, "");

export const options = {
  scenarios: {
    warm_search: {
      executor: "ramping-arrival-rate",
      startRate: 1,
      timeUnit: "1s",
      preAllocatedVUs: 10,
      maxVUs: 50,
      stages: [
        { target: 5, duration: "30s" },
        { target: 15, duration: "2m" },
        { target: 0, duration: "30s" },
      ],
    },
  },
  thresholds: {
    checks: ["rate>0.99"],
    tamiltrove_search_errors: ["rate<0.01"],
    tamiltrove_search_latency: ["p(95)<750", "p(99)<1500"],
  },
};

const queries = [
  "A political courtroom drama about injustice",
  "ஒரே இரவில் நடக்கும் அதிரடி திரைப்படம்",
  "Kaithi maari one night action thriller",
  "Village setting-la emotional family drama",
  "A quiet hidden-gem romance with strong characters",
  "Vijay Sethupathi nadicha crime thriller padam",
];

export default function () {
  const query = queries[(__VU + __ITER) % queries.length];
  const response = http.post(
    `${apiUrl}/api/v1/search`,
    JSON.stringify({
      query,
      filters: {},
      page: 1,
      page_size: 10,
      diversity: 0.3,
    }),
    {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      tags: { route: "search", language: /[\u0B80-\u0BFF]/.test(query) ? "ta" : "mixed" },
      timeout: "10s",
    },
  );

  searchLatency.add(response.timings.duration);
  const passed = check(response, {
    "search returns 200": (result) => result.status === 200,
    "search returns metadata": (result) => {
      try {
        const payload = result.json();
        return Boolean(payload.meta?.request_id && payload.meta?.ranking_version);
      } catch {
        return false;
      }
    },
    "results include grounded explanations": (result) => {
      try {
        const payload = result.json();
        return (payload.results || []).every(
          (movie) => movie.explanation?.summary && Array.isArray(movie.explanation?.evidence),
        );
      } catch {
        return false;
      }
    },
  });
  searchErrors.add(!passed);
  sleep(0.25);
}
