import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import hashlib
import os
from dotenv import load_dotenv
from threading import Lock

# Load environment variables
load_dotenv()

# SMTP configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "no-reply@cariyawallet.com")

# In-memory storage for verification codes with thread-safe access
verification_codes = {}
verification_lock = Lock()

def generate_verification_code() -> str:
    """Generate a 6-digit verification code."""
    return ''.join(random.choices(string.digits, k=6))

def store_verification_code(identifier: str, code: str) -> None:
    """Store verification code in memory with a 5-minute expiration."""
    with verification_lock:
        verification_codes[identifier] = {
            "code": code,
            "expires_at": datetime.now() + timedelta(minutes=5)
        }

def validate_verification_code(identifier: str, code: str) -> bool:
    """Validate the verification code and check expiration."""
    with verification_lock:
        if identifier not in verification_codes:
            return False
        stored = verification_codes[identifier]
        if datetime.now() > stored["expires_at"]:
            del verification_codes[identifier]
            return False
        if stored["code"] != code:
            return False
        del verification_codes[identifier]
        return True

def send_verification_email(identifier: str, code: str) -> None:
    """Send verification code to the specified email address."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"SMTP credentials not set. Simulated sending code {code} to {identifier}")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = identifier
    msg['Subject'] = "Cariya Wallet Verification Code"

    body = f"""
    Dear Cariya Wallet Partner,

    Your verification code is: {code}

    This code is valid for 5 minutes. Please enter it in the Cariya Wallet Partner Portal to complete your login.

    If you did not request this code, please ignore this email.

    Best regards,
    Cariya Wallet Team
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, identifier, msg.as_string())
        print(f"Verification code {code} sent to {identifier}")
    except Exception as e:
        print(f"Failed to send email to {identifier}: {str(e)}")
        raise Exception(f"Failed to send verification email: {str(e)}")

def generate_token(partner_id: str) -> str:
    """Generate a simple token (not secure; use JWT in production)."""
    return hashlib.sha256(f"{partner_id}:{os.urandom(16).hex()}".encode()).hexdigest()