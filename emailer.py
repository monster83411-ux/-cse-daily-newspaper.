"""emailer.py - sends the PDF by Gmail (SMTP with an App Password)."""

import os
import smtplib
import ssl
from email.message import EmailMessage

import config


def build_message(subject, body, pdf_path=None):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = (
        subject,
        config.GMAIL_USER,
        config.RECIPIENT_EMAIL,
    )
    msg.set_content(body)
    if pdf_path:
        with open(pdf_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="pdf",
                filename=os.path.basename(pdf_path),
            )
    return msg


def send(msg):
    for name in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL"):
        if not getattr(config, name):
            raise RuntimeError(
                f"Secret {name} is missing. Add it in GitHub > Settings > Secrets."
            )
    with smtplib.SMTP_SSL(
        "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30
    ) as s:
        s.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        s.send_message(msg)


def send_pdf(subject, body, pdf_path):
    send(build_message(subject, body, pdf_path))


def send_alert(subject, body):
    """A short plain-text email used when something breaks."""
    send(build_message(subject, body))
