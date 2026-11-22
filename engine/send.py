"""Send a rendered issue to the list, one message per recipient (BCC-free)."""
import hashlib
import hmac
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote

from engine.common import GMAIL_USER, GMAIL_APP_PASSWORD, require, subscribers


UNSUBSCRIBE = "https://heist-signup.kevin-murawinski.workers.dev/unsubscribe"
UNSUB_SLOT = "%%UNSUBSCRIBE%%"  # the template's footer link; filled per recipient


def unsubscribe_url(email):
    """A personal unsubscribe link. The signup Worker checks the same HMAC, so
    nobody can unsubscribe anyone else. The key is derived from the Gmail app
    password because the send step already has it (the Worker holds a copy as
    UNSUB_KEY); rotating that password retires old links."""
    key = hashlib.sha256(f"heist-unsubscribe:{GMAIL_APP_PASSWORD}".encode()).hexdigest()
    email = email.strip().lower()
    mac = hmac.new(key.encode(), email.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{UNSUBSCRIBE}?e={quote(email)}&t={mac}"


def send_issue(subject: str, html: str, sender_name: str = "the heist", recipients=None):
    """Send to the list, or to an explicit recipients override (test sends)."""
    require("GMAIL_USER", GMAIL_USER)
    require("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD)

    recipients = recipients or subscribers()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        for i, to in enumerate(recipients):
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = formataddr((sender_name, GMAIL_USER))
            msg["To"] = to
            # Gives Gmail/Apple Mail a native unsubscribe button; with the
            # -Post header Gmail unsubscribes in one click (RFC 8058).
            unsub = unsubscribe_url(to)
            msg["List-Unsubscribe"] = f"<{unsub}>, <mailto:{GMAIL_USER}?subject=unsubscribe>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
            msg.set_content("This issue is best viewed as HTML.")
            msg.add_alternative(html.replace(UNSUB_SLOT, unsub), subtype="html")
            smtp.send_message(msg)
            if i and i % 50 == 0:
                time.sleep(2)  # be gentle with Gmail at larger list sizes
    return len(recipients)
