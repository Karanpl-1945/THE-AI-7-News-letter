"""Sends the weekly newspaper via Gmail SMTP — HTML in body + PDF attachment."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Optional


def send_newspaper(html_content: str, pdf_path: Optional[str], issue_date: str) -> bool:
    sender   = os.environ.get("EMAIL_SENDER", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    recipient= os.environ.get("EMAIL_RECIPIENT", sender)
    user     = os.environ.get("USER_NAME", "Reader")

    if not sender or not password:
        print("[Email] EMAIL_SENDER or EMAIL_PASSWORD not set. Skipping.")
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"⚡ THE AI 7 — Your weekly AI intelligence brief · {issue_date}"
    msg["From"]    = f"THE AI 7 <{sender}>"
    msg["To"]      = recipient

    # HTML body
    html_part = MIMEMultipart("alternative")
    html_part.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(html_part)

    # PDF attachment (if generated)
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        pdf_attach = MIMEApplication(pdf_data, _subtype="pdf")
        pdf_attach.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
        msg.attach(pdf_attach)

    try:
        print(f"[Email] Sending to {recipient}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"[Email] Sent successfully to {recipient}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[Email] Authentication failed. Check EMAIL_SENDER and EMAIL_PASSWORD (use a Gmail App Password).")
        return False
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False
