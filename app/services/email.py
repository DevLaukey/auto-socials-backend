import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")


def is_smtp_configured() -> bool:
    """Check if SMTP is properly configured."""
    return all([SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM])


def send_password_reset_email(to_email: str, token: str) -> bool:
    """
    Send password reset email.
    Returns True if sent successfully, False otherwise.
    """
    if not is_smtp_configured():
        logger.warning(f"SMTP not configured. Reset token for {to_email}: {token}")
        return False

    reset_link = f"{FRONTEND_BASE_URL}/reset-password?token={token}"

    subject = "Reset your password"
    body = f"""
    Hi,

    You requested a password reset.

    Click the link below to reset your password:
    {reset_link}

    This link will expire in 30 minutes.

    If you did not request this, you can safely ignore this email.

    — Your App Team
    """

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {to_email}: {e}")
        return False
