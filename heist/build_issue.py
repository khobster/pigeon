"""Assemble today's heist, archive it to docs/, and optionally send it.

Usage:
  python -m heist.build_issue                       # build + archive only (dry run)
  python -m heist.build_issue --send                # build + archive + send to the list
  python -m heist.build_issue --test you@email.com  # build + send to one address only
"""
import io
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image

from engine.render import render
from heist.sources import (met, cleveland, smk, si, commons, nga, rijks, yale,
                           wellcome, europeana, nypl, chunklet, loc, lam)
from heist import curator

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ARCHIVE_URL = "https://heist.arugulamotors.com/"
HEADER_WEB = "assets/header.png"


UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"}
OUTBOX = ROOT / ".outbox.json"
PINNED = ROOT / "heist" / "pinned"  # heist/pinned/<date>.json overrides the build

# A ledger of recently-fenced loot so the thief doesn't keep stealing the same
# pieces. Keyed by each artwork's source image url (stable + unique per work),
# valued by the date last used. We exclude anything used inside the window at
# build time and record the new issue's loot afterward; the daily workflow's
# existing commit picks up the file because record_art stages it in CI.
RECENT = ROOT / "state" / "recent_art.json"
RECENT_DAYS = 60


def recent_loot(today):
    """Return (ledger, set-of-keys) of art used within the last RECENT_DAYS,
    pruning anything older so the file can't grow without bound."""
    try:
        ledger = json.loads(RECENT.read_text())
    except Exception:  # noqa: BLE001  (missing or corrupt -> start clean)
        return {}, set()
    cutoff = today - timedelta(days=RECENT_DAYS)
    fresh = {}
    for key, used in ledger.items():
        try:
            if date.fromisoformat(used) >= cutoff:
                fresh[key] = used
        except (TypeError, ValueError):
            continue
    return fresh, set(fresh)


def record_art(today, keys, ledger):
    """Stamp this issue's art into the ledger and persist it, staging the file
    so the workflow's archive commit carries it to the next day. Only the real
    CI build writes — local dry runs and previews read the ledger (so they
    avoid recent art) but must never record their throwaway picks into it."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for key in keys:
        if key:
            ledger[key] = today.isoformat()
    RECENT.parent.mkdir(parents=True, exist_ok=True)
    RECENT.write_text(json.dumps(ledger, indent=0, sort_keys=True))
    subprocess.run(["git", "add", str(RECENT)], check=False)


def resized(url, width=1120):
    """The wsrv.nl image CDN, used only to fetch a smaller render at build
    time. Width 1120 = retina-sharp at the 560px layout."""
    return f"https://wsrv.nl/?url={quote(url, safe='')}&w={width}&fit=inside"


def probe_ok(url):
    """True if the URL serves an actual image to a normal client right now."""
    try:
        r = requests.get(url, timeout=25, headers=UA, stream=True)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
        r.close()
        return ok
    except Exception:  # noqa: BLE001
        return False


def all_live(urls, timeout=300):
    """Poll until every url serves an image, or the timeout lapses."""
    deadline = time.time() + timeout
    for u in urls:
        while not probe_ok(u):
            if time.time() > deadline:
                return False
            print(f"  waiting for {u.rsplit('/', 1)[-1]}...")
            time.sleep(15)
    return True


def retrigger_pages(attempt):
    """Nudge GitHub Pages to redeploy by pushing an empty commit.

    Pages occasionally fails its OWN deploy with a transient 401 and never
    retries; any push to the branch starts a fresh deploy. We only do this
    inside CI (where a checkout token and git identity already exist) — never
    on a local --wait-live, which must not push."""
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", f"retrigger Pages deploy (attempt {attempt})"],
        check=True,
    )
    subprocess.run(["git", "pull", "--rebase", "--autostash"], check=True)
    subprocess.run(["git", "push"], check=True)


def color_stats(content, crop=0.70):
    """Measure an image's color. Returns (vivid_frac, hues, cold, sat) where
    vivid_frac is the share of saturated pixels, hues is how many of 12 hue
    buckets are lit, cold is how many of those are outside the warm sepia family
    (buckets 0/1/11), and sat is the mean saturation of the vivid pixels. Returns
    None if the bytes won't decode.

    We shrink the image and look only at the central `crop` fraction, because
    museum photogravures and mounted prints are scanned WITH their cream paper
    mats and pencil annotations, and a warm-toned border alone can light up
    enough hues to sneak a grayscale photograph past a naive check. Cropping to
    the middle judges the art itself; a genuine color piece is color all the way
    in. This one measurement feeds both is_color (the pass/fail gate) and
    wow_score (how bold the loot is)."""
    try:
        im = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    if crop and crop < 1:
        w, h = im.size
        margin = (1 - crop) / 2
        im = im.crop((int(w * margin), int(h * margin),
                      int(w * (1 - margin)), int(h * (1 - margin))))
    im.thumbnail((72, 72))
    hsv = im.convert("HSV").tobytes()
    n = len(hsv) // 3
    if not n:
        return None
    floor = max(2, 0.02 * n)
    bins = [0] * 12
    vivid = 0
    sat_sum = 0
    for i in range(0, len(hsv), 3):
        h, s, v = hsv[i], hsv[i + 1], hsv[i + 2]
        if s >= 60 and 30 <= v <= 235:
            vivid += 1
            sat_sum += s
            bins[(h * 12) // 256] += 1
    hues = sum(1 for b in bins if b >= floor)
    WARM = (0, 1, 11)
    cold = sum(1 for k in range(12) if bins[k] >= floor and k not in WARM)
    sat = (sat_sum / vivid / 255) if vivid else 0.0
    return vivid / n, hues, cold, sat


def is_color(content, min_vivid=0.05, min_hues=2, crop=0.70):
    """True if the image is genuinely in color, not black-and-white.

    The thief only fences color: vivid loot, no grayscale photographs or
    engravings and no sepia scans either. Real color art lights up more than
    one hue bucket, or a single COOL one (blue-and-white porcelain is real
    loot); neutral grayscale has no saturated pixels at all, and a sepia or
    otherwise warm single-tone scan lights up exactly one warm bucket and is
    dropped. If the bytes won't decode we don't second-guess a file that
    already arrived as a valid image.

    Blue-and-white porcelain lights up only one bucket, so the plain hues>=2
    rule would throw it out with the sepia. The thing sepia can never be is
    COLD: a grayscale photo on cream paper, a sanguine drawing and a brown scan
    all live in the red/orange/brown buckets. So we also pass a piece whose
    single lit hue is cool — blue, green, cyan, purple."""
    stats = color_stats(content, crop)
    if stats is None:
        return True
    vivid_frac, hues, cold, _sat = stats
    return vivid_frac >= min_vivid and (hues >= min_hues or cold >= 1)


# Devotional religious art — Madonnas, crucifixions, saints, Hindu and
# Buddhist deities, Qur'an folios — is a huge slice of museum holdings, but it
# reads as heavy, preachy loot for a one-minute palate cleanser. We skip it by
# title across every museum. The terms are deliberately broad and a false
# positive only costs us a resample (the haul redraws cheaply), so we err
# toward dropping anything that smells devotional; classical mythology
# (Venus, Cupid, Apollo) is intentionally NOT here — it reads as decorative,
# not preachy. Word boundaries keep place names safe ("St." abbreviations
# excepted, which is fine — Saint-named towns are rare loot anyway).
RELIGIOUS = re.compile(
    r"\b("
    r"christ|jesus|crucifix\w*|crucified|madonna|piet[aà]|annunciation|"
    r"nativity|resurrection|ascension|assumption|immaculate|epiphany|"
    r"apostle|evangelist|gospel|trinity|saviou?r|sacred heart|ecce homo|"
    r"hail mary|ave maria|mater dolorosa|"
    r"lamentation|deposition|entombment|altarpiece|virgin|saint|saints|st\.|"
    r"holy|angel|archangel|adoration|magi|baptism|prophet|"
    r"qur'?an|koran|sura[h]?|"
    r"krishna|vishnu|shiva|brahma|ganesh\w*|durga|lakshmi|parvati|"
    r"buddha|buddhist|bodhisattva|avalokiteshvara|guanyin|kuan-yin|"
    r"tirthankara|deity|deities|"
    # non-English devotional terms so a foreign-language title can't sneak a
    # saint or a crucifixion past an English-only filter (e.g. SMK's Danish
    # "Sankt Hieronymus", a German "Heilige", an Italian "Madonna in gloria").
    r"sankt|sanct|sainte|santo|santa|hl\.|heilig\w*|"
    r"kristus|cristo|krist\w+|"
    r"jomfru|vierge|vergine|virgen|"
    r"kors\b|kreuz|croce|cruz\b"
    r")\b",
    re.I,
)


# The "St." saint abbreviation can't ride inside RELIGIOUS: that pattern ends
# with a trailing \b, and "St." is followed by a space (a non-word char after a
# non-word "."), so \b never matches and every "St. So-and-so" slipped through
# (e.g. the St. Elisabeth wedding feast that led an issue). Match it separately,
# capital S required so it's the saint abbreviation, not a stray "st".
_SAINT_ABBR = re.compile(r"\bSt\.?\s+[A-Z]")


def secular(title):
    """False for devotional religious subjects, which the heist won't fence."""
    t = title or ""
    return not (RELIGIOUS.search(t) or _SAINT_ABBR.search(t))


# Racist, colonial, and demeaning material — a real hazard in old poster and
# ephemera collections. The "human zoo" circus posters (Hagenbeck and his kind
# exhibited colonized people as spectacle), minstrelsy, blackface, ethnic slurs,
# and "savage/exotic-races" framing all read as museum-catalog-neutral in a title
# but are dehumanizing, and the heist will not send them. Caught by title here;
# the art director (which sees the actual image) is told to reject the rest,
# including visual caricatures a keyword can't catch. Terms are the unambiguous
# ones — we lean on the curator for anything subtler rather than over-filter
# legitimate work by or about the groups these slurs target.
OFFENSIVE = re.compile(
    r"\b("
    r"hagenbeck|v[oö]lkerschau|human zoo|ethnographic (show|exhibition|village)|"
    r"exotic (races|peoples)|savages?|wild (men|people)|missing link|"
    r"minstrel|blackface|black-face|pickaninn\w*|golliwog\w*|sambo|"
    r"\bcoon\b|darkey|darkie|\bdarky\b|mammy|jim crow|plantation melodies|"
    r"pygm\w+|cannibal\w*|head-?hunter|redskin\w*|\bsquaw\w*|"
    r"chinaman|chinamen|jap\b|oriental spectacle"
    r")\b",
    re.I,
)


def inoffensive(title):
    """False for racist / colonial-spectacle / demeaning subjects by title."""
    return not OFFENSIVE.search(title or "")


# The heist used to default to old-master oil portraits because the source pools
# were painting-heavy. Kevin's call: ration the traditional look — a classic
# oil/tempera painting OR a single-sitter portrait in ANY medium — to a rare
# treat, and let eclectic loot (posters, prints, ukiyo-e, ceramics, textiles,
# design, illustration) lead the rest of the week. is_rationed catches both; on
# an ordinary day vet() rejects them and the haul resamples toward something
# wilder. Restricting the paintings gate to oil/tempera alone let dull portrait
# lithographs and portrait miniatures walk right in, so the portrait test is by
# title/medium and medium-agnostic.
CLASSIC_PAINT = re.compile(r"\b(oil|tempera)\b", re.I)
# A single-sitter portrait: an explicit "portrait", a "bust of", or an honorific
# that flags a named individual ("Mrs.", "Madame", "Herr", "Fru"...). Broad on
# purpose — a false positive only costs a resample toward wilder loot.
PORTRAIT = re.compile(
    r"\b(self[- ]?)?portr[ae]it\b|\bbust of\b|\bmrs?\.|\bmme\b|\bmlle\b|"
    r"\bmadame\b|\bmonsieur\b|\bherr\b|\bfru\b|\bfrau\b|\bsir\b|\blord\b|"
    r"\blady\b|\bmiss\b|\bminiature\b",
    re.I,
)


def is_classic_painting(candidate):
    """True for an old-master oil/tempera painting."""
    return bool(CLASSIC_PAINT.search(candidate.get("medium") or ""))


def is_portrait(candidate):
    """True for a single-sitter portrait in any medium — the 'old time portrait'
    look, whether it's an oil, a lithograph or a miniature."""
    text = (candidate.get("title") or "") + " " + (candidate.get("medium") or "")
    return bool(PORTRAIT.search(text))


def is_rationed(candidate):
    """The traditional look we save for a treat day: a classic painting or a
    portrait of any medium."""
    return is_classic_painting(candidate) or is_portrait(candidate)


def is_treat_day(today):
    """About one day in seven the thief may lead with the traditional look (a
    classic painting or a portrait). Date-seeded so it drifts across the week
    instead of always landing on the same weekday."""
    return random.Random("classic-" + today.isoformat()).random() < 1 / 7


# Bucket a piece by medium so the haul mixes forms instead of stacking five oil
# portraits. Commons reports its category as the medium ("chromolithographs",
# "ukiyo-e"); the museum APIs report a real medium string ("Woodblock print",
# "Porcelain"). We read the medium and the title together and take the first
# bucket that matches — order matters (prints before drawings so an ink-and-
# color woodblock lands in "print", not "drawing").
_MEDIUM_BUCKETS = [
    ("poster",    r"poster|affiche|placard"),
    # photo before print: an "albumen silver print" is a photograph, but the
    # print bucket's \bprint would otherwise claim it first.
    ("photo",     r"photograph|gelatin|albumen|daguerreotype|photogravure|collotype|photochrom"),
    ("print",     r"woodblock|woodcut|ukiyo|lithograph|chromolith|etching|engrav|"
                  r"aquatint|mezzotint|linocut|screenprint|\bprint|trade card|"
                  r"cigarette card|playing card|matchbox"),
    ("ceramic",   r"porcelain|ceramic|stoneware|earthenware|terracotta|faience|pottery|\bware\b"),
    ("textile",   r"textile|tapestry|embroider|silk|weav|quilt|\brug\b|carpet|kimono|"
                  r"costume|fashion|garment|\blace\b"),
    ("design",    r"glass|silver|\bgold\b|bronze|furniture|chair|lamp|clock|jewel|enamel|"
                  r"lacquer|wallpaper|netsuke|\bfan\b|screen|mask|arm[ou]r|sword|design"),
    ("sculpture", r"sculptur|marble|statue|\bbust\b|relief|carv"),
    ("drawing",   r"watercolo|gouache|drawing|pastel|chalk|charcoal|graphite|"
                  r"ink and|illustration|botanical"),
    ("painting",  r"oil|tempera|acrylic|fresco|canvas|painting"),
]


def medium_class(candidate):
    text = ((candidate.get("medium") or "") + " " + (candidate.get("title") or "")).lower()
    for name, pat in _MEDIUM_BUCKETS:
        if re.search(pat, text):
            return name
    return "other"


# Titles and artist names arrive as raw catalog strings — filename-derived
# ("Wood Block Printing 08"), doubled ("Unknown author Unknown author"), or
# trailing biographical dates ("born Philadelphia 1875-died 1918"). We tidy them
# so every credit reads like a museum wall label. Kept conservative: a real
# title is left alone, and any over-reach only costs a slightly plainer caption.
_UNKNOWN = re.compile(
    r"^(unknown( author| artist| maker)?|anon(ymous)?|anoniem|unidentified|"
    r"not known|n/?a)\.?$", re.I)
# Words that can legitimately precede a trailing number, so we don't turn
# "Symphony No 5" into "Symphony No".
_ORDINAL = re.compile(r"\b(no|nr|op|opus|vol|part|book|act|scene|plate|fig|figure|pl)\.?$", re.I)


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def tidy_title(title):
    t = _ws((title or "").replace("_", " "))
    t = re.sub(r"\bLCCN\s*\d+\b", "", t, flags=re.I)      # library accession codes
    t = re.sub(r"\b[A-Z]{2,4}[-\s]?\d{4,}\b", "", t)      # museum accession codes
    t = _ws(t)
    if " " not in t and "-" in t:                          # pure filename with hyphens
        t = t.replace("-", " ")
    m = re.search(r"\s+(\d{1,3})$", t)                     # trailing file-sequence number
    if m and not _ORDINAL.search(t[:m.start()]):
        t = t[:m.start()].rstrip()
    if t and t == t.upper() and any(c.isalpha() for c in t):  # ALLCAPS -> Title Case
        t = t.title()
    if len(t) > 90:                                        # trim an overlong description
        breaks = [i for i in (t.find(". "), t.find(": "), t.find("; ")) if 20 < i < 90]
        if breaks:
            t = t[:min(breaks)]
    return t.strip(" .,:;-") or "Untitled"


def tidy_artist(artist):
    a = re.sub(r"^(.+?)\s+\1$", r"\1", _ws(artist))        # collapse a doubled name
    a = re.sub(r",?\s*\b(born|geb\.?|approximately|active|fl\.?|c\.|ca\.|died)\b.*$",
               "", a, flags=re.I)
    a = _ws(a).strip(" ,.;")
    return "Unknown" if (not a or _UNKNOWN.match(a)) else a


def tidy(candidate):
    """Clean a candidate's title and artist in place, then return it."""
    candidate["title"] = tidy_title(candidate.get("title"))
    candidate["artist"] = tidy_artist(candidate.get("artist"))
    return candidate


# Bold, graphic forms that read "hit them in the face" even before we look at
# the pixels — posters, ukiyo-e, chromolithographs. A small nudge; the real
# signal is the measured color.
_BOLD_FORM = re.compile(r"poster|affiche|woodblock|woodcut|ukiyo|chromolith", re.I)


def wow_score(candidate, stats):
    """Rate a candidate for wall-punch, so a morning's draw keeps the most vivid
    loot instead of the first thing that merely passed. stats is a color_stats
    tuple (vivid_frac, hues, cold, sat). The score is dominated by how saturated
    and colorful the image actually is — a pale scientific engraving scores near
    zero while a saturated poster or a bold woodblock scores high — with a small
    bonus for the bold graphic forms and a penalty for the traditional portrait
    look we are trying to ration down."""
    vivid_frac, hues, cold, sat = stats
    score = vivid_frac + 0.5 * vivid_frac * sat + 0.15 * min(hues, 6) / 6.0
    text = (candidate.get("medium") or "") + " " + (candidate.get("title") or "")
    if _BOLD_FORM.search(text):
        score += 0.20
    if is_rationed(candidate):
        score -= 0.40
    return score


def thumb_stats(url):
    """Fetch a small render of a candidate and return its color_stats, or None.
    Cheap enough to run over a whole pool of candidates so wow_score can rank
    them before we commit to the full-resolution download of the winner."""
    try:
        r = requests.get(resized(url, 240), timeout=20, headers=UA)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            return None
        return color_stats(r.content)
    except Exception:  # noqa: BLE001
        return None


# Muted line-work: engravings, etchings, drawings and the like. These read as
# old-timey and monochrome even when a scan carries a little tint, and one kept
# winning the hero slot. Banned from the hero outright, and from the bag, so the
# issue stays loud. (Woodblock/woodcut are NOT here — ukiyo-e is vivid loot.)
MUTED_FORM = re.compile(
    r"engrav|etch|mezzotint|drypoint|silverpoint|\bpencil\b|graphite|"
    r"charcoal|\bdrawing\b|\bsketch\b",
    re.I,
)


def _muted(candidate):
    return bool(MUTED_FORM.search((candidate.get("medium") or "") + " " + (candidate.get("title") or "")))


def hero_worthy(candidate, stats):
    """The hero has to be LOUD: no muted line-work, and genuinely saturated
    across more than one hue (or a single vivid cool hue). This is the bar that
    keeps a tinted engraving out of the hero slot — the thing Kevin kept seeing.
    A dull scan scores vivid_frac near 0.05; a poster or ukiyo-e clears 0.15
    easily."""
    vivid_frac, hues, cold, sat = stats
    if _muted(candidate):
        return False
    return vivid_frac >= 0.15 and (hues >= 3 or (cold >= 1 and sat >= 0.5))


def punchy(candidate, stats):
    """The bag bar: still no muted line-work and clearly in color, a notch below
    the hero so the issue keeps some variety without going dull."""
    vivid_frac, hues, cold, sat = stats
    if _muted(candidate):
        return False
    return vivid_frac >= 0.08 and (hues >= 2 or cold >= 1)


def in_color(candidate, stats):
    """The fallback bar (same as is_color) so the issue still ships on a night
    when nothing loud can be found."""
    vivid_frac, hues, cold, sat = stats
    return vivid_frac >= 0.05 and (hues >= 2 or cold >= 1)


def verified(url, today, tag, width=1120):
    """Download the image and return a URL on OUR domain, or raise.

    This is the whole guarantee. Every image in the email is a file we
    physically hold and serve from heist.arugulamotors.com, so once it is
    confirmed live on Pages it cannot break when the email is opened later,
    no matter what a museum server or CDN does in the meantime. A piece
    whose bytes we cannot fetch — or that turns out to be black-and-white —
    gets dropped; the manifest never lists loot the thief could not actually
    carry out, and the haul is always in color.

    Per attempt we try the wsrv-resized render first (smaller file), then
    the origin directly. Retries with backoff because some origins (Harvard)
    rate-limit datacenter IPs like the GitHub runner."""
    if not url:
        raise RuntimeError("no image url")
    art_dir = DOCS / "assets" / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    last, content, ctype = None, None, None
    for attempt in range(4):
        for candidate in (resized(url, width), url):
            try:
                resp = requests.get(candidate, timeout=45, headers=UA)
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if not ctype.startswith("image/"):
                    raise RuntimeError(f"not an image: {ctype or 'unknown'}")
                content = resp.content
                break
            except Exception as e:  # noqa: BLE001
                last = e
        if content is not None:
            break
        time.sleep(10 * (attempt + 1))
    if content is None:
        raise RuntimeError(f"could not fetch {url}: {last}")
    # Retrying a grayscale image would just refetch the same bytes, so this
    # check sits outside the retry loop and drops the piece straight away.
    if not is_color(content):
        raise RuntimeError(f"black-and-white, want color: {url}")
    ext = ".png" if "png" in ctype else ".jpg"
    name = f"{today.isoformat()}-{tag}{ext}"
    (art_dir / name).write_bytes(content)
    return f"{ARCHIVE_URL}assets/art/{name}"


def vet(candidate, recent, seen, allow_traditional=True):
    """Reject loot we can't fence: recently shown, religious, a repeat within
    this issue, or — unless it's a treat day — the traditional look (a classic
    painting or a portrait). Returns the dedup key (the source image url)."""
    key = candidate.get("image")
    if not key:
        raise RuntimeError("no image url")
    if key in seen:
        raise RuntimeError("already in this issue")
    if key in recent:
        raise RuntimeError(f"shown in the last {RECENT_DAYS} days: {candidate.get('title')}")
    if not secular(candidate.get("title")):
        raise RuntimeError(f"religious subject: {candidate.get('title')}")
    if not inoffensive(candidate.get("title")):
        raise RuntimeError(f"racist/demeaning subject: {candidate.get('title')}")
    if not allow_traditional and is_rationed(candidate):
        raise RuntimeError(f"traditional look held for a treat day: {candidate.get('title')}")
    return key


def build_haul(rng, today, extras_wanted=8, recent=frozenset()):
    """One hero piece plus a bag of companions from the other museums. Returns
    (hero, extras, used_keys) where used_keys feeds the recently-shown ledger."""
    # A broad bench of open-access sources so no single museum dominates and a
    # dead one is never fatal. Commons is the always-on anchor (keyless, images
    # on upload.wikimedia.org, which never blocks datacenter IPs); nga is a
    # bundled CC0 pool; rijks/yale/wellcome are keyless live APIs. si and
    # europeana are key-gated and only join the rotation when their key is set —
    # europeana alone aggregates 3,000+ institutions. AIC and Harvard were
    # retired 2026-07-14 (both hard-block the runner's IP with 403/429 and had
    # contributed no art for weeks); their modules stay in the tree in case the
    # blocks ever lift.
    museums = ([met, cleveland, smk, commons, nga, rijks, yale, wellcome]
               + [m for m in (si, europeana, nypl) if m.available()])
    start = today.toordinal() % len(museums)
    rotation = museums[start:] + museums[:start]

    used, seen = [], set()

    def thumb(url):
        """Fetch a candidate's small render, returning (bytes, color_stats) or
        (None, None). We keep the bytes so the art director can look at them."""
        try:
            r = requests.get(resized(url, 240), timeout=20, headers=UA)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/"):
                return None, None
            return r.content, color_stats(r.content)
        except Exception:  # noqa: BLE001
            return None, None

    # Gather a broad pool of vetted, in-color candidates and KEEP their
    # thumbnails so the art director can judge them by eye. We no longer ration
    # paintings or portraits here (allow_traditional=True) — a cool Cezanne or a
    # Modigliani is exactly the point; the curator decides what's cool. Religious
    # subjects, recent repeats, and within-issue dupes are still filtered by vet.
    pool, keys, draws = [], set(), 0

    def try_add(museum, source):
        """Draw one candidate from a source; add it to the pool (tagged with the
        source) if it vets and is in color. Returns True on add."""
        nonlocal draws
        draws += 1
        try:
            c = museum.steal(rng)
            key = vet(c, recent, set(), allow_traditional=True)
            if key in keys or key in seen:
                return False
            content, stats = thumb(c["image"])
            if stats is None or not in_color(c, stats):
                return False
            keys.add(key)
            pool.append({"candidate": c, "key": key, "image": content, "stats": stats, "source": source})
            return True
        except Exception as e:  # noqa: BLE001
            print(f"  [candidate skipped] {museum.__name__}: {e}")
            return False

    # Pre-seed Europeana so its global eclectica reliably makes each issue rather
    # than only when the round-robin lands on it. Its yield is low (many scans are
    # sepia/monochrome and get dropped as B&W), so we try hard for a few.
    if europeana.available():
        euro_added, euro_tries = 0, 0
        while euro_added < 4 and euro_tries < 22:
            euro_tries += 1
            if try_add(europeana, "europeana"):
                euro_added += 1
        print(f"  [europeana seeded {euro_added} into the pool]")

    # General gather fills the rest of the pool from the full rotation.
    for museum in rotation * 16:
        if len(pool) >= 18 or draws >= 84:
            break
        try_add(museum, museum.__name__.rsplit(".", 1)[-1])
    if not pool:
        raise RuntimeError("no candidate art could be secured tonight")

    # The art director looks at the pool and picks the coolest hero + a ranked
    # bag, to the heist's Barnes/Whitney/MoMA taste. If it is unavailable, fall
    # back to the vividness metric (hero must be loud; bag must be punchy).
    verdict = curator.curate(
        [{"i": i, "image": p["image"],
          **{k: p["candidate"].get(k, "") for k in ("title", "artist", "year", "medium", "museum")}}
         for i, p in enumerate(pool)],
        extras_wanted,
    )
    if verdict:
        print(f"  [art director] hero: {pool[verdict['hero']]['candidate'].get('title', '')[:60]}")
        primary = [verdict["hero"]] + verdict["bag"]
    else:
        ranked = sorted(range(len(pool)),
                        key=lambda i: wow_score(pool[i]["candidate"], pool[i]["stats"]), reverse=True)
        hero_idx = next((i for i in ranked if hero_worthy(pool[i]["candidate"], pool[i]["stats"])),
                        ranked[0])
        primary = [hero_idx] + [i for i in ranked if i != hero_idx
                                and punchy(pool[i]["candidate"], pool[i]["stats"])]
    # Backfill any remaining pool pieces (vividness-ranked) so the bag can still
    # fill even when the curator's bag is short or downloads fail.
    backfill = sorted([i for i in range(len(pool)) if i not in primary],
                      key=lambda i: wow_score(pool[i]["candidate"], pool[i]["stats"]), reverse=True)
    order = primary + backfill

    # Hero: the first piece in order whose full-resolution image downloads.
    hero = None
    for pos, idx in enumerate(order):
        p = pool[idx]
        try:
            p["candidate"]["image"] = verified(p["candidate"]["image"], today, "haul")
        except Exception as e:  # noqa: BLE001
            print(f"  [hero winner failed to download] {e}")
            continue
        hero = tidy(p["candidate"])
        seen.add(p["key"])
        used.append(p["key"])
        order = order[pos + 1:]
        break
    if not hero:
        raise RuntimeError("no hero could be secured tonight")

    # Fill the bag from the rest, medium-diverse (no more than CLASS_CAP of any
    # one form). Front-load up to EUROPEANA_MIN Europeana pieces so its global
    # eclectica reliably appears in the bag, then fill the rest in curator order.
    EUROPEANA_MIN = 2
    euro_first = [i for i in order if pool[i]["source"] == "europeana"][:EUROPEANA_MIN]
    fill_seq = euro_first + [i for i in order if i not in euro_first]

    CLASS_CAP = 3
    counts = {medium_class(hero): 1}
    extras = []
    for idx in fill_seq:
        if len(extras) >= extras_wanted:
            break
        p = pool[idx]
        cls = medium_class(p["candidate"])
        if counts.get(cls, 0) >= CLASS_CAP:
            continue
        try:
            p["candidate"]["image"] = verified(p["candidate"]["image"], today, f"extra{len(extras)}", width=880)
        except Exception as e:  # noqa: BLE001
            print(f"  [extra failed to download] {e}")
            continue
        extras.append(tidy(p["candidate"]))
        counts[cls] = counts.get(cls, 0) + 1
        used.append(p["key"])
        seen.add(p["key"])
    return hero, extras, used


EXTRA_ROW = """
  <tr><td align="center" style="padding:8px 0 10px;">
    <a href="{url}" style="text-decoration:none;"><img src="{image}" alt="{title}" width="440" style="display:block; width:80%; max-width:440px; height:auto; border:0;"></a>
  </td></tr>{take_row}
  <tr><td align="center" style="padding:0 0 18px; font-family:Helvetica, Arial, sans-serif; font-size:12px; color:#999999; line-height:1.5;">
    <strong style="color:#555555;">{title}</strong><br>{artist}{year_part} · <a href="{url}" style="color:#999999; white-space:nowrap;">{museum}</a>
  </td></tr>"""

EXTRA_TAKE = """
  <tr><td align="center" style="padding:2px 0 8px; font-family:Georgia, 'Times New Roman', serif; font-size:14px; font-style:italic; color:#444444; line-height:1.45;">
    {take}
  </td></tr>"""


def extras_html(extras, takes=()):
    if not extras:
        return ""
    rows = ['''
  <tr><td style="padding:0 0 8px; font-family:Helvetica, Arial, sans-serif; font-size:13px; font-weight:bold; color:#555555;">
    also in the bag:
  </td></tr>''']
    for i, e in enumerate(extras):
        title = e["title"] if len(e["title"]) <= 80 else e["title"][:80].rsplit(" ", 1)[0] + "..."
        take = takes[i] if i < len(takes) else ""
        rows.append(EXTRA_ROW.format(
            url=e["url"], image=e["image"], title=title, artist=e["artist"],
            year_part=f", {e['year']}" if e["year"] else "", museum=e["museum"],
            take_row=EXTRA_TAKE.format(take=take) if take else "",
        ))
    rows.append('  <tr><td style="padding:0 0 22px;"></td></tr>')
    return "".join(rows)


VAULT_ROW = """
  <tr><td align="center" style="padding:0 0 8px;">
    <a href="{url}" style="text-decoration:none;"><img src="{image}" alt="{title}" width="560" style="display:block; width:100%; height:auto; border:0;"></a>
  </td></tr>
  <tr><td style="padding:0 0 18px; font-family:Helvetica, Arial, sans-serif; font-size:13px; color:#555555; line-height:1.4;">
    {title}{date_part}<br>
    <span style="font-size:12px; color:#999999;">found in <a href="{url}" style="color:#999999; white-space:nowrap;">the Library of Congress</a></span>
  </td></tr>"""


def vault_html(vaults):
    if not vaults:
        return ""
    rows = []
    for v in vaults:
        rows.append(VAULT_ROW.format(
            url=v.get("url", ""), image=v["image"], title=v.get("title", ""),
            date_part=f', {v["date"]}' if v.get("date") else "",
        ))
    return "".join(rows)


def try_steal(source, rng):
    """Optional sections fail soft: a thin issue still ships."""
    try:
        return source.steal(rng)
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] {source.__name__}: {e}")
        return {}


# Generic catalog language that makes dull loot. The manifest wants the
# gem, so the framing words, the materials, the container shapes and the
# unidentified-portrait boilerplate all get filtered out and whatever rare
# proper noun is left ("Yue", "Hakone", "Dorian") becomes the loot.
SUBJECT_STOP = {
    # framing / grammar
    "the", "from", "with", "and", "for", "also", "known", "series",
    "untitled", "study", "view", "scene", "after", "called", "plate",
    "number", "between", "design", "detail", "group", "set", "pair",
    "model", "picture",
    # generic people
    "portrait", "madame", "monsieur", "saint", "young", "woman", "man",
    "men", "girl", "boy", "child", "head", "figure", "landscape",
    "unidentified", "unknown", "sitter",
    # formats / materials
    "sheet", "panel", "fragment", "album", "leaf", "page", "photograph",
    "photo", "print", "drawing", "painting", "sketch", "poster",
    "lithograph", "etching", "engraving", "watercolor", "still", "life",
    # container shapes
    "covered", "box", "jar", "vase", "dish", "bowl", "cup", "plate",
    "bottle", "vessel", "ware", "lid", "cover", "tile", "statue", "bust",
    "relief",
    # bland modifiers
    "new", "old", "red", "blue", "green", "white", "black", "gold", "two",
    "one", "three", "large", "small", "great", "big",
}


def keyword(text):
    """The most interesting word in a title: a distinctive proper noun, not
    generic catalog language. We keep capitalized words that survive the
    stop list (down to three letters, so 'Yue' and 'Lid' qualify) and, among
    those, take the longest. The manifest, one word per item."""
    words = re.findall(r"[A-Za-z][A-Za-z']*", text or "")
    def norm(w):
        w = w.lower()
        return w[:-2] if w.endswith("'s") else w
    caps = [w for w in words if w[0].isupper() and norm(w) not in SUBJECT_STOP and len(w) >= 3]
    pool = caps or [w for w in words if len(w) >= 5 and norm(w) not in SUBJECT_STOP]
    return max(pool, key=len) if pool else ""


def build_subject(haul, extras, line, vault, hideout):
    texts = (
        [haul["title"] or haul["artist"]]
        + [e["title"] for e in extras]
        + [line.get("work") or line.get("attribution", "")]
        + [vault.get("title") or vault.get("topic", "")]
        + [hideout.get("name", "")]
    )
    words, seen = [], set()
    for t in texts:
        w = keyword(t)
        if w and w.lower() not in seen:
            words.append(w)
            seen.add(w.lower())
    while len(", ".join(words)) > 75 and len(words) > 3:
        words.pop(1)  # shed loot from the middle, keep the hero and the hideout
    return ", ".join(words) or "last night's haul"


def build(today=None):
    today = today or date.today()
    rng = random.Random(today.isoformat())

    ledger, recent = recent_loot(today)

    haul, extras, used = build_haul(rng, today, recent=recent)
    line = try_steal(chunklet, rng)

    # From the Vault: three LoC finds, one per topic for variety. The pool skews
    # heavily to a few topics (WPA + circus + railroad posters), so drawing three
    # at random would routinely show two circus posters; requiring distinct
    # topics guarantees a mix. Each draw dodges recent loot + this issue's art and
    # must actually download; we keep going until we have three or run out of
    # tries, and the section fails soft if fewer are provable.
    vaults, vault_keys = [], []
    tried, vault_topics = set(), set()
    for _ in range(30):
        if len(vaults) >= 3:
            break
        candidate = try_steal(loc, rng)
        if not candidate:
            break
        key = candidate.get("image")
        topic = candidate.get("topic", "")
        if not key or key in recent or key in used or key in tried:
            continue
        tried.add(key)
        # The vault draws straight from the LoC pool and skips vet(), so screen
        # it here: no devotional subjects, and no racist / colonial-spectacle
        # material (the "human zoo" circus posters live in this pool).
        title = candidate.get("title", "")
        if not secular(title) or not inoffensive(title):
            continue
        if topic and topic in vault_topics:
            continue  # one piece per topic — cool variety over three circus posters
        try:
            candidate["image"] = verified(candidate["image"], today, f"vault{len(vaults)}")
            candidate["title"] = tidy_title(candidate.get("title"))
            vaults.append(candidate)
            vault_keys.append(key)
            if topic:
                vault_topics.add(topic)
        except Exception as e:  # noqa: BLE001
            print(f"  [vault redraw, image unprovable] {e}")
    if not vaults:
        print("  [vault dropped: no provable LoC images after resampling]")

    hideout = try_steal(lam, rng)
    if hideout.get("image"):
        try:
            hideout["image"] = verified(hideout["image"], today, "lam")
        except Exception:  # noqa: BLE001
            hideout["image"] = ""  # the hideout survives without a photo

    context = {
        "date_pretty": today.strftime("%B %-d, %Y"),
        "preheader": f"Last night's haul: {haul['title']}",
        "archive_url": ARCHIVE_URL,
        "haul_image": haul["image"],
        "haul_title": haul["title"],
        "haul_artist": haul["artist"],
        "haul_year": haul["year"],
        "haul_medium": haul["medium"],
        "haul_museum": haul["museum"],
        "haul_url": haul["url"],
        "extras_html": extras_html(extras),
        "line_text": line.get("text", ""),
        "line_attr": line.get("attribution") or "lifted from somewhere in the canon",
        "line_summary": line.get("summary", ""),
        "vault_any": bool(vaults),
        "vault_html": vault_html(vaults),
        "lam_name": hideout.get("name", ""),
        "lam_blurb": hideout.get("blurb", ""),
        "lam_image": hideout.get("image", ""),
        "lam_url": hideout.get("url", ""),
    }

    template = (ROOT / "heist" / "template.html").read_text()
    email_html = render(template, {**context, "header_src": ARCHIVE_URL + HEADER_WEB})
    archive_html = render(template, {**context, "header_src": "../" + HEADER_WEB})

    subject = build_subject(haul, extras, line, vaults[0] if vaults else {}, hideout)
    record_art(today, used + vault_keys, ledger)
    return subject, email_html, archive_html, today


def prune_old_art(today, keep_days=365):
    """Delete self-hosted art older than a year. The live email is never
    affected; only archive pages past keep_days go text-only. Keeps the
    repo under the GitHub Pages size limit with zero maintenance."""
    art_dir = DOCS / "assets" / "art"
    if not art_dir.exists():
        return
    removed = 0
    for f in art_dir.glob("*-*.*"):
        stamp = f.name[:10]
        try:
            age = (today - date.fromisoformat(stamp)).days
        except ValueError:
            continue
        if age > keep_days:
            f.unlink()
            removed += 1
    if removed:
        print(f"pruned {removed} art file(s) older than {keep_days} days")


def write_archive(archive_html, today):
    issues_dir = DOCS / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    (issues_dir / f"{today.isoformat()}.html").write_text(archive_html)

    issues = sorted(issues_dir.glob("*.html"), reverse=True)

    def pretty(stem):
        try:
            return date.fromisoformat(stem).strftime("%B %-d, %Y")
        except ValueError:
            return stem

    items = "\n".join(
        f'      <li><a href="issues/{p.name}">{pretty(p.stem)}</a></li>' for p in issues
    )
    n = len(issues)
    count_line = f"{n} heist{'s' if n != 1 else ''} and counting"
    index = (ROOT / "docs" / "_index_template.html").read_text()
    (DOCS / "index.html").write_text(
        index.replace("{{count_line}}", count_line).replace("{{issue_list}}", items)
    )
    print(f"archived issue {today.isoformat()} ({len(issues)} total)")


def main():
    if "--send-outbox" in sys.argv:
        from engine.send import send_issue

        data = json.loads(OUTBOX.read_text())
        n = send_issue(data["subject"], data["html"])
        print(f"sent '{data['subject']}' to {n} subscriber(s)")
        return

    if "--wait-live" in sys.argv:
        # Every image is self-hosted now, so none of them may be sent until
        # all are confirmed live on Pages (Apple Mail prefetches at delivery).
        # If they don't come up, the usual cause is a transient Pages deploy
        # failure (a self-inflicted 401 on GitHub's side) that nothing retries
        # on its own; in CI we retrigger the deploy with an empty commit and
        # wait again, since the send is gated on the art actually being live.
        data = json.loads(OUTBOX.read_text())
        own = [u for u in re.findall(r'<img src="([^"]+)"', data["html"]) if u.startswith(ARCHIVE_URL)]
        for attempt in range(1, 4):
            if all_live(own):
                print(f"all {len(own)} image(s) live on our domain")
                return
            if not os.environ.get("GITHUB_ACTIONS"):
                break  # a local run can't (and must not) retrigger a deploy
            print(f"art not live (attempt {attempt}); retriggering the Pages deploy")
            retrigger_pages(attempt)
        sys.exit("timed out waiting for the art to deploy")

    if "--test-outbox" in sys.argv:
        from engine.send import send_issue

        to = sys.argv[sys.argv.index("--test-outbox") + 1]
        data = json.loads(OUTBOX.read_text())
        send_issue(data["subject"], data["html"], recipients=[to])
        print(f"test: sent '{data['subject']}' to {to} only")
        return

    # A pinned edition (heist/pinned/<date>.json, with subject/email_html/
    # archive_html) locks a specific hand-approved issue for that day instead
    # of regenerating it. The nightly build is not fully reproducible — The
    # Line is drawn fresh each run and the chunklet Lambda can be down — so
    # this is how we guarantee a particular issue goes out. Its art is already
    # live, so the usual publish/wait-live/send steps still apply unchanged.
    pin = PINNED / f"{date.today().isoformat()}.json"
    if pin.exists():
        data = json.loads(pin.read_text())
        write_archive(data["archive_html"], date.today())
        OUTBOX.write_text(json.dumps({"subject": data["subject"], "html": data["email_html"]}))
        print(f"using pinned edition for {date.today().isoformat()}: '{data['subject']}'")
        return

    # Building downloads every image into docs/. Because all art is now
    # self-hosted, sending can ONLY happen after the archive is pushed and
    # the images are confirmed live (--wait-live), so there is no immediate
    # --send/--test path: everything goes through the outbox.
    subject, email_html, archive_html, today = build()
    write_archive(archive_html, today)
    prune_old_art(today)
    OUTBOX.write_text(json.dumps({"subject": subject, "html": email_html}))
    if "--prepare" in sys.argv:
        print(f"prepared '{subject}' into the outbox")
    else:
        print(f"dry run: '{subject}' built and archived, not sent")


if __name__ == "__main__":
    main()
