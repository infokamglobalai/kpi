from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def send_email_smtp(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Send an email using SMTP.

    Works with AWS SES SMTP or any SMTP relay.
    """
    host = os.getenv("EPMS_SMTP_HOST", "").strip()
    port = int(os.getenv("EPMS_SMTP_PORT", "587").strip() or "587")
    username = os.getenv("EPMS_SMTP_USERNAME", "").strip()
    password = os.getenv("EPMS_SMTP_PASSWORD", "").strip()
    mail_from = os.getenv("EPMS_EMAIL_FROM", "").strip()
    use_starttls = _env_bool("EPMS_SMTP_STARTTLS", True)

    if not host:
        return False, "Missing EPMS_SMTP_HOST."
    if not mail_from:
        return False, "Missing EPMS_EMAIL_FROM."
    if not to_email.strip():
        return False, "Recipient email is required."

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = to_email.strip()
    msg["Subject"] = subject.strip() or "EPMS Notification"
    msg.set_content(body or "")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host=host, port=port, timeout=20) as server:
            server.ehlo()
            if use_starttls:
                server.starttls(context=context)
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        return True, "Email sent."
    except Exception as exc:  # noqa: BLE001
        return False, f"Email failed: {exc}"

