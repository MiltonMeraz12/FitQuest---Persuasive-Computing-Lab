const SCHEMA_SQL = `
  CREATE TABLE IF NOT EXISTS wearable_latest (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    received_at INTEGER NOT NULL
  )
`;

let schemaReady = false;

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
        ...payload,
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
