// Signups and unsubscribes for the heist, straight against the subscriber
// sheet the daily send reads from.
//   POST /             the homepage form: append the email (dupes skipped), and
//                      pass it to Formspree so Kevin gets an email about it.
//   GET  /unsubscribe  the footer link in every issue: a confirm page (link
//                      scanners follow GETs, so a GET never removes anyone).
//   POST /unsubscribe  the confirm button, or Gmail's one-click unsubscribe
//                      (RFC 8058): remove the row. Links carry an HMAC of the
//                      email (engine/send.py) so nobody can remove anyone else.
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
    const url = new URL(req.url);
    if (url.pathname === "/unsubscribe") return unsubscribe(req, url, env, ctx);
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
      const { base, auth } = await sheetApi(env);
      const api = `${base}/values`;
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

async function sheetApi(env) {
  const token = await googleToken(JSON.parse(env.GOOGLE_SA));
  return { base: `https://sheets.googleapis.com/v4/spreadsheets/${env.SHEET_ID}`, auth: { Authorization: `Bearer ${token}` } };
}

async function sign(env, email) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.UNSUB_KEY),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email)));
  return [...mac].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

const page = (title, body, status = 200) => new Response(`<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title><link rel="icon" href="https://heist.arugulamotors.com/favicon.ico">
<style>body{margin:0;background:#fff;color:#1a1a1a;font-family:Helvetica,Arial,sans-serif;text-align:center}
.w{max-width:440px;margin:0 auto;padding:64px 20px}.m{font-family:Georgia,serif;font-style:italic;font-size:32px;margin:0 0 6px}
img{width:120px;height:auto;margin:10px 0 24px}p{font-size:16px;line-height:1.6;color:#333}
button{font:800 14px Helvetica,Arial,sans-serif;letter-spacing:1px;text-transform:uppercase;padding:13px 24px;background:#ffe95e;color:#111;border:0;cursor:pointer;margin-top:8px}
a{color:#1a1a1a}</style></head><body><div class="w"><p class="m">the heist</p>
<img src="https://heist.arugulamotors.com/assets/header-tall.webp" alt="">${body}</div></body></html>`,
  { status, headers: { "Content-Type": "text/html; charset=utf-8" } });

const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

async function unsubscribe(req, url, env, ctx) {
  const email = (url.searchParams.get("e") || "").trim().toLowerCase();
  const ok = email && (url.searchParams.get("t") || "") === (await sign(env, email));
  if (!ok) {
    return page("the heist", `<p>That link looks bent. Reply "unsubscribe" to any issue and the thief will take you off by hand.</p>`, 400);
  }
  if (req.method === "GET") {
    return page("Call off the heist?", `<p>Call off the heist for <b>${esc(email)}</b>?</p>
<form method="post"><button type="submit">Yes, call it off</button></form>
<p style="font-size:14px;color:#8a8a8a;margin-top:28px">Changed your mind? Just close this page.</p>`);
  }
  try {
    const { base, auth } = await sheetApi(env);
    const meta = await (await fetch(`${base}?fields=sheets.properties`, { headers: auth })).json();
    const sheetId = meta.sheets[0].properties.sheetId;
    const col = await (await fetch(`${base}/values/A:A`, { headers: auth })).json();
    const rows = (col.values || []).map((r, i) => [String(r[0] || "").trim().toLowerCase(), i])
      .filter(([e]) => e === email).map(([, i]) => i).reverse();  // bottom up, so indexes hold
    if (rows.length) {
      const r = await fetch(`${base}:batchUpdate`, {
        method: "POST", headers: { ...auth, "Content-Type": "application/json" },
        body: JSON.stringify({ requests: rows.map((i) => ({ deleteDimension: {
          range: { sheetId, dimension: "ROWS", startIndex: i, endIndex: i + 1 } } })) }),
      });
      if (!r.ok) throw new Error(`delete ${r.status}: ${await r.text()}`);
      const note = new FormData();
      note.set("email", email);
      note.set("product", "heist-unsubscribe");
      note.set("note", "Unsubscribed. Already removed from the sheet, nothing to do.");
      ctx.waitUntil(fetch(FORMSPREE, { method: "POST", headers: { Accept: "application/json" }, body: note }).catch(() => {}));
    }
  } catch (e) {
    console.log("unsubscribe failed", String(e));
    return page("the heist", `<p>Something jammed. Try the link again in a minute, or reply "unsubscribe" to any issue.</p>`, 502);
  }
  return page("Heist called off", `<p>Done. <b>${esc(email)}</b> is off the list, and no more heists will arrive.</p>
<p>Miss it? <a href="https://heist.arugulamotors.com/">Get your thief back</a> anytime.</p>`);
}

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
