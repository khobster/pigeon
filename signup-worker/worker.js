// Signups for the heist: the homepage form posts here, and the email lands
// straight in the subscriber sheet the daily send reads from. Duplicates are
// skipped, and each new thief is also passed to Formspree so Kevin gets an
// email about it.
const ORIGINS = ["https://heist.arugulamotors.com", "http://localhost:8765"];
const FORMSPREE = "https://formspree.io/f/mvzyogdl";
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export default {
  async fetch(req, env, ctx) {
    const origin = req.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ORIGINS.includes(origin) ? origin : ORIGINS[0],
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (req.method !== "POST") return new Response("the heist signup", { headers: cors });

    const reply = (status, body) =>
      new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });
    let form;
    try {
      form = await req.formData();
    } catch {
      return reply(400, { error: "bad form" });
    }
    if (form.get("website")) return reply(200, { ok: true }); // honeypot: bots fill every field
    const email = String(form.get("email") || "").trim().toLowerCase();
    if (!EMAIL.test(email) || email.length > 200) return reply(400, { error: "bad email" });

    try {
      const token = await googleToken(JSON.parse(env.GOOGLE_SA));
      const api = `https://sheets.googleapis.com/v4/spreadsheets/${env.SHEET_ID}/values`;
      const auth = { Authorization: `Bearer ${token}` };
      const have = await (await fetch(`${api}/A:A`, { headers: auth })).json();
      const known = new Set((have.values || []).map((r) => String(r[0] || "").trim().toLowerCase()));
      if (known.has(email)) return reply(200, { ok: true, already: true });
      const joined = new Date().toISOString().slice(0, 10);
      const r = await fetch(`${api}/A:B:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, {
        method: "POST",
        headers: { ...auth, "Content-Type": "application/json" },
        body: JSON.stringify({ values: [[email, joined]] }),
      });
      if (!r.ok) throw new Error(`append ${r.status}: ${await r.text()}`);
      const note = new FormData();
      note.set("email", email);
      note.set("product", "heist-subscribe");
      note.set("note", `New thief, now in the sheet (${known.size} before them, counting the header).`);
      ctx.waitUntil(fetch(FORMSPREE, { method: "POST", headers: { Accept: "application/json" }, body: note }).catch(() => {}));
      return reply(200, { ok: true });
    } catch (e) {
      console.log("signup failed", String(e));
      return reply(502, { error: "sheet unreachable" });
    }
  },
};

// A short-lived Google access token from the service account (JWT bearer flow).
async function googleToken(sa) {
  const b64 = (s) => btoa(s).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  const now = Math.floor(Date.now() / 1000);
  const head = b64(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = b64(JSON.stringify({
    iss: sa.client_email, scope: "https://www.googleapis.com/auth/spreadsheets",
    aud: "https://oauth2.googleapis.com/token", iat: now, exp: now + 3600,
  }));
  const pem = sa.private_key.replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
  const der = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey("pkcs8", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(`${head}.${claim}`)));
  const jwt = `${head}.${claim}.${b64(String.fromCharCode(...sig))}`;
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=${jwt}`,
  });
  const d = await r.json();
  if (!d.access_token) throw new Error(`token: ${JSON.stringify(d)}`);
  return d.access_token;
}
