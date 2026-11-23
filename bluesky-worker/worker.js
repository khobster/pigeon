// The heist on Bluesky: once the day's email has gone out, post the lead art
// with a link to sign up. The rest of the bag stays a mystery.
//   cron         checks, and posts at most once per issue
//   GET /preview the post it would make right now (no login, no posting)
// The build writes docs/latest.json; the workflow records state/last_sent
// after the send, so a post never gets ahead of the email.
const SITE = "https://heist.arugulamotors.com/";
const LATEST = SITE + "latest.json";
const SENT = "https://raw.githubusercontent.com/khobster/pigeon/main/state/last_sent";
const SERVICE = "https://bsky.social";
const PUBLIC = "https://public.api.bsky.app";
const MAX_BLOB = 950_000;

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(run(env).then((r) => console.log(r), (e) => console.log("failed", String(e))));
  },
  async fetch(req, env) {
    if (new URL(req.url).pathname !== "/preview") return new Response("the heist on bluesky");
    const latest = await getJson(LATEST);
    return Response.json({ sent: await sentDate(), latest: latest.date, text: compose(latest), image: latest.pieces[0].image });
  },
};

async function run(env) {
  if (!env.BSKY_HANDLE || !env.BSKY_APP_PASSWORD) return "no account configured";
  const [latest, sent] = await Promise.all([getJson(LATEST), sentDate()]);
  if (latest.date !== sent) return `waiting: latest ${latest.date}, last sent ${sent}`;
  if (env.START_DATE && latest.date < env.START_DATE) return `holding until ${env.START_DATE}`;
  const tag = `heist${latest.date.replaceAll("-", "")}`;
  if (await alreadyPosted(env.BSKY_HANDLE, tag)) return `already posted ${latest.date}`;

  const s = await xrpc("com.atproto.server.createSession", {
    body: { identifier: env.BSKY_HANDLE, password: env.BSKY_APP_PASSWORD.trim() },
  });
  const images = [];
  for (const p of latest.pieces.slice(0, 1)) {
    try {
      const { bytes, type } = await image(p.image);
      const blob = await upload(s, bytes, type);
      const dims = jpegSize(bytes);
      images.push({ image: blob, alt: alt(p), ...(dims && { aspectRatio: dims }) });
    } catch (e) {
      console.log("image skipped", p.image, String(e));
    }
  }
  const text = compose(latest);
  await xrpc("com.atproto.repo.createRecord", {
    session: s,
    body: {
      repo: s.did, collection: "app.bsky.feed.post",
      record: {
        $type: "app.bsky.feed.post", text, langs: ["en"], tags: [tag],
        createdAt: new Date().toISOString(), facets: facets(text),
        ...(images.length && { embed: { $type: "app.bsky.embed.images", images } }),
      },
    },
  });
  return `posted ${latest.date} with ${images.length} image(s)`;
}

// The caption: the lead piece, where it was lifted from, and the way in. All
// lowercase, the heist's voice. (Alt text keeps real case for screen readers.)
export function compose(latest) {
  const lead = latest.pieces[0];
  const by = lead.artist && !/^(unknown|anonymous)/i.test(lead.artist) ? ` by ${lead.artist}` : "";
  const year = lead.year ? `, ${lead.year}` : "";
  const tail = "\n\nplus a whole lot more in the bag. a free art heist in your inbox every morning: heist.arugulamotors.com";
  const head = (t) => `today's haul: ${t}${by}${year}. lifted from ${place(lead.museum)}.`;
  let title = tidy(lead.title);
  while ([...head(title) + tail].length > 300 && title.length > 20) title = title.slice(0, -10).replace(/\s+\S*$/, "") + "...";
  return (head(title) + tail).toLowerCase();
}

// "Night of the Sokol houses. 11. 9. 2015." -> "Night of the Sokol houses"
function tidy(title) {
  return (title || "Untitled").replace(/[.,]?\s*\b\d{1,2}\.\s?\d{1,2}\.\s?\d{4}\.?\s*$/, "").replace(/[.\s]+$/, "");
}

// "Historical Museum, Czech Republic, via Europeana" -> "the Historical
// Museum, Czech Republic"; "The Cleveland Museum of Art" -> "the Cleveland..."
function place(museum) {
  const m = (museum || "a museum").replace(/,?\s*via Europeana$/, "").replace(/^The /, "the ");
  return /^(Historical|National|Natural|Cultural|Metropolitan|State|Art|Los|Museum|Rijksmuseum)\b/.test(m) ? `the ${m}` : m;
}

function alt(p) {
  const bits = [p.title, p.artist, p.year].filter(Boolean).join(", ");
  return `${bits}. ${p.museum}.`.slice(0, 1000);
}

function facets(text) {
  const enc = new TextEncoder();
  const at = (i) => enc.encode(text.slice(0, i)).length;
  const i = text.indexOf("heist.arugulamotors.com");
  return i < 0 ? [] : [{ index: { byteStart: at(i), byteEnd: at(i) + 23 },
    features: [{ $type: "app.bsky.richtext.facet#link", uri: SITE }] }];
}

async function alreadyPosted(handle, tag) {
  const d = await getJson(`${PUBLIC}/xrpc/app.bsky.feed.getAuthorFeed?actor=${encodeURIComponent(handle)}&limit=10&filter=posts_no_replies`);
  return (d.feed || []).some((f) => (f.post.record.tags || []).includes(tag));
}

// Bluesky caps a blob near 1MB, so shrink through wsrv when the original is big.
async function image(url) {
  for (const u of [url, `https://wsrv.nl/?url=${encodeURIComponent(url)}&w=1400&output=jpg&q=82`]) {
    const r = await fetch(u, { signal: AbortSignal.timeout(20000) });
    if (!r.ok) continue;
    const bytes = new Uint8Array(await r.arrayBuffer());
    if (bytes.length <= MAX_BLOB) return { bytes, type: r.headers.get("content-type") || "image/jpeg" };
  }
  throw new Error("no image small enough");
}

async function upload(s, bytes, type) {
  const r = await fetch(`${SERVICE}/xrpc/com.atproto.repo.uploadBlob`, {
    method: "POST", headers: { Authorization: `Bearer ${s.accessJwt}`, "Content-Type": type }, body: bytes,
  });
  if (!r.ok) throw new Error(`uploadBlob ${r.status}: ${await r.text()}`);
  return (await r.json()).blob;
}

// Width and height from a JPEG's frame header, so Bluesky lays the image out
// at its real shape instead of a square guess.
function jpegSize(b) {
  if (b[0] !== 0xff || b[1] !== 0xd8) return null;
  let i = 2;
  while (i + 9 < b.length) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1], len = (b[i + 2] << 8) | b[i + 3];
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
      return { height: (b[i + 5] << 8) | b[i + 6], width: (b[i + 7] << 8) | b[i + 8] };
    }
    i += 2 + len;
  }
  return null;
}

async function sentDate() {
  const r = await fetch(`${SENT}?t=${Date.now()}`, { cf: { cacheTtl: 0 } });
  return r.ok ? (await r.text()).trim() : "";
}

async function getJson(url) {
  const r = await fetch(url, { signal: AbortSignal.timeout(20000), cf: { cacheTtl: 0 } });
  if (!r.ok) throw new Error(`${url} ${r.status}`);
  return r.json();
}

async function xrpc(method, { session, body } = {}) {
  const r = await fetch(`${SERVICE}/xrpc/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(session && { Authorization: `Bearer ${session.accessJwt}` }) },
    body: JSON.stringify(body), signal: AbortSignal.timeout(20000),
  });
  if (!r.ok) throw new Error(`${method} ${r.status}: ${await r.text()}`);
  return r.json();
}
