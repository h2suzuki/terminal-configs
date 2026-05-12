// claude-dashboard.mjs
//
// Usage:
//   node claude-dashboard.mjs  <dashboard.json> <org-id>
//
// Behavior:
//   1. Load dashboard JSON from a local file.
//   2. Extract dashboard.uuid from the JSON.
//   3. Login to SigNoz using the provisioned root user.
//      - POST /api/v2/sessions/email_password
//   4. Try PUT /api/v1/dashboards/{uuid}.
//      - PUT updates an existing dashboard.
//      - PUT does not create a missing dashboard.
//      - If the dashboard does not exist, SigNoz returns 404.
//   5. On 404 only, fall back to POST /api/v1/dashboards.
//   6. Any non-404 PUT error is treated as a real failure.

import { readFile } from "node:fs/promises";

// Must match with signoz_compose-override.yaml
const SIGNOZ_URL = "http://localhost:14902";
const EMAIL = "admin@signoz.localhost";
const PASSWORD = "At4902.localhost";

const dashboardFile = process.argv[2];
const orgId = process.argv[3];

if (!dashboardFile || !orgId) {
  throw new Error("Usage: node claude-dashboard.mjs <dashboard.json> <org-id>");
}

const log = (message) => process.stdout.write(`${message}\n`);
const spin = (message) => process.stdout.write(`\r${message}`);
const clearLine = () => process.stdout.write("\r\x1b[2K");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function api(method, path, body, token) {
  const res = await fetch(`${SIGNOZ_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body == null ? undefined : JSON.stringify(body),
  });

  const text = await res.text();

  if (!res.ok) {
    const error = new Error(`${method} ${path}: ${res.status} ${text}`);
    error.status = res.status;
    throw error;
  }

  const contentType = res.headers.get("content-type") ?? "";

  if (!contentType.includes("application/json")) {
    throw new Error(
      `${method} ${url}: JSON expected, got ${res.status} ${contentType}: ${text.slice(0, 200)}`
    );
  }

  return text ? JSON.parse(text) : null;
}

async function login() {
  const frames = ["|", "/", "-", "\\"];
  let lastError = null;

  for (let i = 0; i < 180; i++) {
    spin(`\r${frames[i % frames.length]} Waiting for SigNoz login API...`);

    try {
      const res = await api("POST", "/api/v2/sessions/email_password", {
        email: EMAIL,
        password: PASSWORD,
        orgId,
      });

      const token = res.data?.accessToken;

      if (token) {
        clearLine(); log("Logged in");
        return token;
      }

      lastError = new Error(`Session response did not contain data.accessToken: ${JSON.stringify(res)}`);

    } catch(error) {
      lastError = error;    // SigNoz may still be starting after docker compose up.
    }

    await sleep(1000);
  }

  clearLine();
  throw lastError ?? new Error("Login failed");
}

const dashboard = JSON.parse(await readFile(dashboardFile, "utf8"));
const dashboardUuid = dashboard.uuid;

if (!dashboardUuid) {
  throw new Error("Dashboard JSON must contain top-level uuid");
}

const token = await login();

try {
  await api("PUT", `/api/v1/dashboards/${dashboardUuid}`, dashboard, token);
  log(`Dashboard updated: ${dashboardUuid}`);
} catch (error) {
  if (error.status !== 404) throw error;

  await api("POST", "/api/v1/dashboards", dashboard, token);
  log(`Dashboard created: ${dashboardUuid}`);
}
