"""One line a day from Kevin, collected by email, for the J. Paul Squishy column.

Each morning, right after the issue goes out, the heist's Gmail asks Kevin
for tomorrow's line ("hobs for Wednesday, November 25"). He replies whenever
he likes; within about 15 minutes `--proof` (its own workflow) answers with
the clipping exactly as it will print and whether it fits the box. The next
morning's build reads the inbox, takes his latest reply (only his address,
only one Gmail signed for), keeps the whole sentences that fit the box's 13
lines, and heist/squishy.py prints it as a newspaper clipping. "skip", or no
reply at all, and the column sits out that day.
"""
import email
import imaplib
import re
import sys
from datetime import datetime, timedelta
from email.utils import formataddr, parseaddr, parsedate_to_datetime
from zoneinfo import ZoneInfo

from engine.common import GMAIL_USER, GMAIL_APP_PASSWORD

KEVIN = "kevin.murawinski@gmail.com"
MAX_CHARS = 1200          # far past the box; only guards against a pasted essay
PROOFED = "squishy-proofed"  # Gmail label on a reply that has had its proof
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


def ask(day):
    """Email Kevin for the line that runs on `day`."""
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = subject_for(day)
    msg["From"] = formataddr(("the heist", GMAIL_USER))
    msg["To"] = KEVIN
    msg.set_content(
        f"Reply with your line for {day:%A}'s heist. About 55 to 60 words fills "
        "the box (13 lines); whole sentences past that get left on the floor.\n\n"
        "Within about 15 minutes you'll get a proof back showing exactly how it prints.\n"
        "Reply again to change it; the newest reply wins.\n\n"
        "Reply \"skip\", or don't reply, and the column sits out.\n"
        "Replies count until the issue goes out that morning.\n"
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
    """Kevin's line for `day`, fitted to the box, or "" (no reply, a skip,
    or the inbox is out of reach)."""
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
        print("  [hobs: no reply, column sits out]")
        return ""
    line = clean(_body(_latest(replies)[1]))
    if _is_skip(line):
        print("  [hobs: skipped]")
        return ""
    line, dropped, need = fit(line)
    if dropped:
        print(f"  [hobs: {need} lines, left off] {dropped}")
    return line


def _proof_note(day, line):
    if _is_skip(line):
        return f"Got it: skip. The column sits out {day:%A}.\n", None
    from heist import squishy

    printed, dropped, need = fit(line)
    again = "Reply again to change it; the newest reply wins."
    if not dropped:
        room = squishy.LINES - need
        more = f" Room for about {room * 5} more words." if room >= 2 else ""
        note = f"Fits: {need} of {squishy.LINES} lines.{more} This is how it prints {day:%A}.\n\n{again}\n"
    else:
        tail = printed.split()[-3:]
        note = (f"Runs {need - squishy.LINES} line{'s' if need - squishy.LINES > 1 else ''} past the box "
                f"({need} lines, the box holds {squishy.LINES}), so it prints through "
                f"\"...{' '.join(tail)}\" and leaves off:\n\n    {dropped}\n\n"
                f"Trim it to get it all in. {again}\n")
    return note, squishy.render(printed, seed=day.toordinal())


def proof():
    """Answer each new reply with its clipping, exactly as it will print."""
    import smtplib
    from email.message import EmailMessage

    now = datetime.now(ZoneInfo("America/New_York"))
    days = [now.date() + timedelta(days=1)]
    if now.hour < 7:  # this morning's issue hasn't gone out yet
        days.insert(0, now.date())
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    imap.select("INBOX")
    for day in days:
        replies = _replies(imap, day)
        if not replies:
            continue
        i, msg = _latest(replies)
        _, data = imap.fetch(i, "(X-GM-LABELS)")
        if PROOFED in data[0].decode("utf-8", "replace"):
            continue
        note, jpg = _proof_note(day, clean(_body(msg)))
        out = EmailMessage()
        subj = msg["Subject"] or subject_for(day)
        out["Subject"] = subj if subj.lower().startswith("re:") else "Re: " + subj
        out["From"] = formataddr(("the heist", GMAIL_USER))
        out["To"] = KEVIN
        if msg["Message-ID"]:
            out["In-Reply-To"] = msg["Message-ID"]
            out["References"] = " ".join(filter(None, [msg["References"], msg["Message-ID"]]))
        out.set_content(note)
        if jpg:
            out.add_attachment(jpg, maintype="image", subtype="jpeg", filename=f"squishy-{day.isoformat()}.jpg")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.send_message(out)
        imap.store(i, "+X-GM-LABELS", f"({PROOFED})")
        print(f"proofed {day}: {note.splitlines()[0]}")
    imap.logout()


if __name__ == "__main__":
    if "--proof" in sys.argv:
        proof()
