"""Send a rendered issue to the list, one message per recipient (BCC-free)."""
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr

from engine.common import GMAIL_USER, GMAIL_APP_PASSWORD, require, subscribers


def send_issue(subject: str, html: str, sender_name: str = "the heist"):
    require("GMAIL_USER", GMAIL_USER)
    require("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD)

    recipients = subscribers()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        for i, to in enumerate(recipients):
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = formataddr((sender_name, GMAIL_USER))
            msg["To"] = to
            # Gives Gmail/Apple Mail a native unsubscribe affordance and
            # keeps bulk-sender reputation healthy as the list grows.
            msg["List-Unsubscribe"] = f"<mailto:{GMAIL_USER}?subject=unsubscribe>"
            msg.set_content("This issue is best viewed as HTML.")
            msg.add_alternative(html, subtype="html")
            smtp.send_message(msg)
            if i and i % 50 == 0:
                time.sleep(2)  # be gentle with Gmail at larger list sizes
    return len(recipients)
