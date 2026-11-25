"""One line a day from Kevin, collected by email, for the J. Paul Squishy column.

Each morning, right after the issue goes out, the heist's Gmail asks Kevin
for tomorrow's line ("hobs for Wednesday, November 25") with a link to his
desk (docs/desk/), a page that sets the line as he types, counts it against
the box's 13 lines, and saves it to the heist-desk Worker. Replying to the
email still works as a backup (only his address, only one Gmail signed for);
a desk save wins over a reply. The next morning's build keeps the whole
sentences that fit the box, and heist/squishy.py prints it as a newspaper
clipping. "skip", or nothing saved, and the column sits out that day.
"""
import email
import hashlib
import hmac
import imaplib
import re
from datetime import timedelta
from email.utils import formataddr, parseaddr, parsedate_to_datetime

import requests

from engine.common import GMAIL_USER, GMAIL_APP_PASSWORD

KEVIN = "kevin.murawinski@gmail.com"
MAX_CHARS = 1200          # far past the box; only guards against a pasted essay
DESK = "https://heist.arugulamotors.com/desk/"
WORKER = "https://heist-desk.kevin-murawinski.workers.dev/line"
ABBREV = re.compile(r"\b(Mr|Mrs|Ms|Dr|St|Jr|Sr|vs|Mt|No)\.$")

QUOTE_START = [
    re.compile(r"^on\b.*(wrote|écrit):?\s*$", re.I),
    re.compile(r"^-{2,}\s*(original message|forwarded message)?", re.I),
    re.compile(r"^(sent from my|get outlook)", re.I),
    re.compile(r"^>"),
    re.compile(r"^__+$"),
]


def subject_for(day):
    return f"hobs for {day:%A, %B} {day.day}"


def _desk_k(day):
    """The heist-desk Worker checks the same HMAC (its DESK_KEY secret)."""
    key = hashlib.sha256(f"heist-desk:{GMAIL_APP_PASSWORD}".encode()).hexdigest()
    return hmac.new(key.encode(), f"desk:{day.isoformat()}".encode(), hashlib.sha256).hexdigest()[:32]


def desk_link(day):
    return f"{DESK}?d={day.isoformat()}&k={_desk_k(day)}"


def from_desk(day):
    """What Kevin saved at his desk for `day`, or None (nothing saved, or the
    Worker is out of reach)."""
    try:
        r = requests.get(WORKER, params={"d": day.isoformat(), "k": _desk_k(day)}, timeout=20)
        r.raise_for_status()
        return r.json().get("line")
    except Exception as e:  # noqa: BLE001
        print(f"  [hobs: desk unreachable] {e}")
        return None


def ask(day):
    """Email Kevin for the line that runs on `day`."""
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = subject_for(day)
    msg["From"] = formataddr(("the heist", GMAIL_USER))
    msg["To"] = KEVIN
    msg.set_content(
        f"Your desk for {day:%A}'s heist:\n\n{desk_link(day)}\n\n"
        "Type your line there and watch it set. About 55 to 60 words fills the box "
        "(13 lines); whole sentences past that get left on the floor.\n\n"
        "Save as often as you like until the issue goes out that morning. "
        "Save \"skip\", or nothing, and the column sits out.\n"
        "(Replying to this email still works too, but a desk save wins.)\n"
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def _body(msg):
    plain = html = ""
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        try:
            text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        if part.get_content_type() == "text/plain" and not plain:
            plain = text
        elif part.get_content_type() == "text/html" and not html:
            html = text
    if not plain and html:
        html = re.sub(r"(?is)<blockquote.*", "", html)  # Gmail's quoted thread
        html = re.sub(r"(?i)<br\s*/?>|</(p|div)>", "\n", html)
        plain = re.sub(r"<[^>]+>", "", html)
    return plain


def clean(text):
    """His words only: no quoted thread, no signature."""
    lines = text.replace("\r", "").split("\n")
    keep = []
    for i, line in enumerate(lines):
        s = line.strip()
        # Gmail wraps a long "On ... wrote:" across two lines
        joined = s + " " + (lines[i + 1].strip() if i + 1 < len(lines) else "")
        if any(p.match(s) for p in QUOTE_START) or (s.lower().startswith("on ") and joined.rstrip().endswith("wrote:")):
            break
        keep.append(s)
    line = " ".join(" ".join(keep).split()).replace("&nbsp;", " ").strip()
    if len(line) > MAX_CHARS:
        line = line[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return line


def sentences(text):
    out = []
    for piece in re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+(?=[A-Z0-9\"'“‘(])", text):
        if out and ABBREV.search(out[-1]):
            out[-1] += " " + piece  # "Mr. Rogers" is one sentence
        else:
            out.append(piece)
    return out


def fit(text):
    """(what prints, what's left off, lines the whole reply needs): the whole
    sentences that fit the box; a first sentence too long alone is cut short."""
    from heist import squishy

    need = squishy.lines_needed(text)
    if need <= squishy.LINES:
        return text, "", need
    parts, kept = sentences(text), []
    for s in parts:
        if squishy.lines_needed(" ".join(kept + [s])) > squishy.LINES:
            break
        kept.append(s)
    if not kept:
        words = parts[0].split()
        while words and squishy.lines_needed(" ".join(words) + "...") > squishy.LINES:
            words.pop()
        kept_text = " ".join(words).rstrip(",;:") + "..."
        return kept_text, text[len(" ".join(words)):].strip(), need
    return " ".join(kept), " ".join(parts[len(kept):]), need


def _genuine(msg):
    """From Kevin, and Gmail itself says so (a forged From fails DMARC)."""
    if parseaddr(msg.get("From", ""))[1].lower() != KEVIN:
        return False
    auth = " ".join(msg.get_all("Authentication-Results") or [])
    return "dmarc=pass" in auth or ("dkim=pass" in auth and "header.i=@gmail.com" in auth)


def _is_skip(line):
    return not line or line.lower().strip(" .!") == "skip"


def _replies(imap, day):
    """[(imap id, message)] of Kevin's genuine replies for `day`."""
    since = (day - timedelta(days=3)).strftime("%d-%b-%Y")
    _, ids = imap.search(None, "FROM", f'"{KEVIN}"', "SUBJECT", f'"{subject_for(day)}"', "SINCE", since)
    out = []
    for i in ids[0].split():
        _, data = imap.fetch(i, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        if _genuine(msg):
            out.append((i, msg))
    return out


def _latest(replies):
    return max(replies, key=lambda r: parsedate_to_datetime(r[1]["Date"]))  # a second reply is a correction


def collect(day):
    """Kevin's line for `day`, fitted to the box, or "" (nothing saved, no
    reply, a skip, or neither the desk nor the inbox in reach)."""
    line = from_desk(day)
    if line is None:
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            imap.select("INBOX", readonly=True)
            replies = _replies(imap, day)
            imap.logout()
        except Exception as e:  # noqa: BLE001
            print(f"  [hobs: inbox unreachable, column sits out] {e}")
            return ""
        if not replies:
            print("  [hobs: nothing saved and no reply, column sits out]")
            return ""
        line = clean(_body(_latest(replies)[1]))
    line = " ".join(line.split())
    if _is_skip(line):
        print("  [hobs: skipped]")
        return ""
    line, dropped, need = fit(line)
    if dropped:
        print(f"  [hobs: {need} lines, left off] {dropped}")
    return line
