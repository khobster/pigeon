"""One line a day from Kevin, collected by email, for the J. Paul Squishy column.

Each morning, right after the issue goes out, the heist's Gmail asks Kevin
for tomorrow's line ("hobs for Wednesday, November 25"). He replies whenever
he likes. The next morning's build reads the inbox, takes his reply (only his
address, only one Gmail signed for) and keeps the first two sentences;
heist/squishy.py prints it as a newspaper clipping. "skip", or no reply at
all, and the column sits out that day.
"""
import email
import imaplib
import re
from datetime import timedelta
from email.utils import formataddr, parseaddr, parsedate_to_datetime

from engine.common import GMAIL_USER, GMAIL_APP_PASSWORD

KEVIN = "kevin.murawinski@gmail.com"
MAX_CHARS = 320
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
        f"Reply with your line for {day:%A}'s heist. One or two sentences; "
        "anything past the second gets left on the floor.\n\n"
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
    """His words only: no quoted thread, no signature, two sentences at most."""
    lines = text.replace("\r", "").split("\n")
    keep = []
    for i, line in enumerate(lines):
        s = line.strip()
        # Gmail wraps a long "On ... wrote:" across two lines
        joined = s + " " + (lines[i + 1].strip() if i + 1 < len(lines) else "")
        if any(p.match(s) for p in QUOTE_START) or (s.lower().startswith("on ") and joined.rstrip().endswith("wrote:")):
            break
        keep.append(s)
    words = " ".join(" ".join(keep).split())
    words = words.replace("&nbsp;", " ").strip()
    sentences = []
    for piece in re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+(?=[A-Z0-9\"'“‘(])", words):
        if sentences and ABBREV.search(sentences[-1]):
            sentences[-1] += " " + piece  # "Mr. Rogers" is one sentence
        else:
            sentences.append(piece)
    line = " ".join(sentences[:2]).strip()
    if len(line) > MAX_CHARS:
        line = line[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return line


def _genuine(msg):
    """From Kevin, and Gmail itself says so (a forged From fails DMARC)."""
    if parseaddr(msg.get("From", ""))[1].lower() != KEVIN:
        return False
    auth = " ".join(msg.get_all("Authentication-Results") or [])
    return "dmarc=pass" in auth or ("dkim=pass" in auth and "header.i=@gmail.com" in auth)


def collect(day):
    """Kevin's line for `day`, or "" (no reply, a skip, or the inbox is out of reach)."""
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX", readonly=True)
        since = (day - timedelta(days=3)).strftime("%d-%b-%Y")
        _, ids = imap.search(None, "FROM", f'"{KEVIN}"', "SUBJECT", f'"{subject_for(day)}"', "SINCE", since)
        replies = []
        for i in ids[0].split():
            _, data = imap.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            if _genuine(msg):
                replies.append(msg)
        imap.logout()
    except Exception as e:  # noqa: BLE001
        print(f"  [hobs: inbox unreachable, column sits out] {e}")
        return ""
    if not replies:
        print("  [hobs: no reply, column sits out]")
        return ""
    latest = max(replies, key=lambda m: parsedate_to_datetime(m["Date"]))  # a second reply is a correction
    line = clean(_body(latest))
    if not line or line.lower().strip(" .!") == "skip":
        print("  [hobs: skipped]")
        return ""
    return line

