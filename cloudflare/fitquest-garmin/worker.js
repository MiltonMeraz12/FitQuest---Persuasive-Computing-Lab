const SCHEMA_SQL = `
  CREATE TABLE IF NOT EXISTS wearable_latest (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    received_at INTEGER NOT NULL
  )
`;

let schemaReady = false;

// Mirrors the passthrough field list in
// tools/garmin_connectiq_http_bridge.py's normalize_connectiq_payload, so
// both bridges accept the same shape and this endpoint stops blindly
// spreading the whole client-supplied payload into storage.
const BASE_FIELDS = ["device_name", "provider", "sample_type", "source", "timestamp", "activity_state"];
const PASSTHROUGH_FIELDS = [
  "heart_rate_bpm",
  "heart_rate_contact",
  "heart_rate_confidence",
  "rr_intervals_ms",
  "hrv_ms",
  "battery",
  "stress",
  "body_battery",
  "respiration_rate",
  "pulse_ox",
  "steps",
  "calories",
  "acceleration",
  "acceleration_unit",
  "acceleration_magnitude_mg",
  "watch_motion_delta_mg",
  "watch_motion_state",
  "gyroscope",
  "gyroscope_unit",
  "location",
  "latitude",
  "longitude",
  "altitude_m",
  "speed_mps",
  "distance_m",
  "heading_deg",
  "sequence",
  "sent_count",
  "sample_interval_ms",
  "endpoint_mode",
  "last_http_code",
  "battery_unit",
  "note",
];
const MIN_PLAUSIBLE_HEART_RATE_BPM = 20;
const MAX_PLAUSIBLE_HEART_RATE_BPM = 240;

function sanitizeHeartRateBpm(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  if (numeric < MIN_PLAUSIBLE_HEART_RATE_BPM || numeric > MAX_PLAUSIBLE_HEART_RATE_BPM) return null;
  return Math.round(numeric);
}

function normalizePayload(raw) {
  const payload = { status: "connected", device: "garmin_venu_3" };
  for (const key of BASE_FIELDS) {
    if (raw[key] !== undefined && raw[key] !== null) payload[key] = raw[key];
  }
  for (const key of PASSTHROUGH_FIELDS) {
    if (raw[key] !== undefined && raw[key] !== null) payload[key] = raw[key];
  }
  if ("heart_rate_bpm" in payload) {
    const sanitized = sanitizeHeartRateBpm(payload.heart_rate_bpm);
    if (sanitized === null) delete payload.heart_rate_bpm;
    else payload.heart_rate_bpm = sanitized;
  }
  return payload;
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function ensureSchema(env) {
  if (schemaReady) return;
  await env.FITQUEST_DB.prepare(SCHEMA_SQL).run();
  schemaReady = true;
}

function dbMissingResponse() {
  return jsonResponse(
    {
      status: "error",
      project: "FitQuest",
      message: "Missing D1 binding FITQUEST_DB.",
    },
    503,
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/" || url.pathname === "/health") {
      return jsonResponse({
        status: "ok",
        project: "FitQuest",
        service: "Garmin telemetry relay",
        storage: env.FITQUEST_DB ? "d1" : "missing_d1_binding",
      });
    }

    if (!env.FITQUEST_DB) return dbMissingResponse();

    if (url.pathname === "/garmin" && request.method === "POST") {
      // Opt-in auth: only enforced once FITQUEST_SHARED_TOKEN is configured
      // as a Worker secret (`wrangler secret put FITQUEST_SHARED_TOKEN`), so
      // an unconfigured deploy keeps accepting telemetry exactly as before
      // instead of silently locking it out. Send the same value from the
      // Connect IQ app as an `X-FitQuest-Token` header once configured.
      if (env.FITQUEST_SHARED_TOKEN && request.headers.get("x-fitquest-token") !== env.FITQUEST_SHARED_TOKEN) {
        return jsonResponse({ status: "error", message: "Missing or invalid X-FitQuest-Token header." }, 401);
      }

      let payload;
      try {
        payload = await request.json();
      } catch (error) {
        return jsonResponse({ status: "error", message: "Invalid JSON payload." }, 400);
      }

      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return jsonResponse({ status: "error", message: "Payload must be a JSON object." }, 400);
      }

      await ensureSchema(env);
      const stored = {
        ...normalizePayload(payload),
        project: "fitquest",
        bridge_received_at: new Date().toISOString(),
      };
      await env.FITQUEST_DB.prepare(
        `INSERT INTO wearable_latest (id, payload, received_at)
         VALUES (1, ?, ?)
         ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, received_at = excluded.received_at`,
      )
        .bind(JSON.stringify(stored), Date.now())
        .run();

      return jsonResponse({ status: "ok", project: "FitQuest" });
    }

    if (url.pathname === "/latest" && request.method === "GET") {
      await ensureSchema(env);
      const row = await env.FITQUEST_DB
        .prepare("SELECT payload, received_at FROM wearable_latest WHERE id = 1")
        .first();
      if (!row) {
        return jsonResponse({ status: "waiting", project: "FitQuest" }, 404);
      }

      try {
        const payload = JSON.parse(row.payload);
        return jsonResponse({ ...payload, bridge_received_epoch_ms: row.received_at });
      } catch (error) {
        return jsonResponse({ status: "error", message: "Stored payload is invalid." }, 500);
      }
    }

    return jsonResponse({ status: "not_found", project: "FitQuest" }, 404);
  },
};
