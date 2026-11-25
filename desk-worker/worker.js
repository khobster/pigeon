// J. Paul Squishy's desk: holds the line Kevin types at heist.arugulamotors.com/desk/
// until the morning build picks it up.
//   GET  /line?d=YYYY-MM-DD&k=...   the saved line for that day (or none)
//   POST /line {d, k, line}         save it (the newest save wins)
// k is an HMAC of the day (heist/hobs.py desk_link), so the link in the
// morning ask email only ever opens that one day's line.
const ORIGINS = ["https://heist.arugulamotors.com", "http://localhost:8765"];
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const MAX_CHARS = 1200;

async function sign(key, msg) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ORIGINS.includes(origin) ? origin : ORIGINS[0],
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Cache-Control": "no-store",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    const reply = (status, body) =>
      new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });
    const url = new URL(req.url);
    if (url.pathname !== "/line") return reply(404, { error: "not here" });

    let d, k, body;
    if (req.method === "POST") {
      try {
        body = await req.json();
      } catch {
        return reply(400, { error: "bad json" });
      }
      ({ d, k } = body);
    } else {
      d = url.searchParams.get("d");
      k = url.searchParams.get("k");
    }
    if (!DAY.test(String(d || "")) || !k || k !== (await sign(env.DESK_KEY, `desk:${d}`)))
      return reply(403, { error: "this link doesn't open that day" });

    if (req.method === "GET") {
      const saved = await env.DESK.get(`line:${d}`, "json");
      return reply(200, saved || { line: null });
    }
    if (req.method !== "POST") return reply(405, { error: "GET or POST" });
    const line = String(body.line ?? "").replace(/\s+/g, " ").trim().slice(0, MAX_CHARS);
    const saved = { line, saved: new Date().toISOString() };
    // a line nobody picked up for a month is gone on its own
    await env.DESK.put(`line:${d}`, JSON.stringify(saved), { expirationTtl: 60 * 60 * 24 * 30 });
    return reply(200, { ok: true, ...saved });
  },
};
