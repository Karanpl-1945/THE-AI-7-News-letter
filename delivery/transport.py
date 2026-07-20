"""Swappable email transport — Gmail SMTP today, an ESP (SES/Resend) later."""

from __future__ import annotations

import os
import smtplib
from abc import ABC, abstractmethod
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


class EmailTransport(ABC):
    """A destination-agnostic way to deliver one HTML email with an optional PDF."""

    @abstractmethod
    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        pdf_path: Optional[str] = None,
        pdf_filename: Optional[str] = None,
    ) -> bool:
        """Send one email, returning whether delivery succeeded."""


def _build_message(
    *,
    sender: str,
    sender_name: str,
    to: str,
    subject: str,
    html: str,
    pdf_path: Optional[str],
    pdf_filename: Optional[str],
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to

    html_part = MIMEMultipart("alternative")
    html_part.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(html_part)

    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        pdf_attach = MIMEApplication(pdf_data, _subtype="pdf")
        pdf_attach.add_header(
            "Content-Disposition",
            "attachment",
            filename=pdf_filename or os.path.basename(pdf_path),
        )
        msg.attach(pdf_attach)

    return msg


class GmailSMTPTransport(EmailTransport):
    """Sends mail through a Gmail account's SMTP-over-SSL endpoint."""

    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        pdf_path: Optional[str] = None,
        pdf_filename: Optional[str] = None,
    ) -> bool:
        sender = os.environ.get("EMAIL_SENDER", "")
        password = os.environ.get("EMAIL_PASSWORD", "")
        sender_name = os.environ.get("USER_NAME", "THE AI 7") or "THE AI 7"

        if not sender or not password:
            print("[Email] EMAIL_SENDER or EMAIL_PASSWORD not set. Skipping.")
            return False

        msg = _build_message(
            sender=sender,
            sender_name=sender_name,
            to=to,
            subject=subject,
            html=html,
            pdf_path=pdf_path,
            pdf_filename=pdf_filename,
        )

        try:
            print(f"[Email] Sending to {to}...")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender, password)
                server.sendmail(sender, to, msg.as_string())
            print(f"[Email] Sent successfully to {to}")
            return True
        except smtplib.SMTPAuthenticationError:
            print("[Email] Authentication failed. Check EMAIL_SENDER and EMAIL_PASSWORD (use a Gmail App Password).")
            return False
        except Exception as e:
            print(f"[Email] Error sending to {to}: {e}")
            return False


def get_email_transport() -> EmailTransport:
    """Return the configured transport. Only Gmail SMTP exists today."""
    transport_name = os.environ.get("EMAIL_TRANSPORT", "gmail_smtp").strip().lower()
    if transport_name == "gmail_smtp":
        return GmailSMTPTransport()
    raise ValueError(f"Unknown EMAIL_TRANSPORT: {transport_name!r}")
