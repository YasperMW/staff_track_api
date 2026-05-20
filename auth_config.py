import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "This is required for JWT token signing. "
        "Set it in your .env file or environment before starting the server."
    )

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
MAX_FAILED_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
NOTIFY_AFTER_FAILED_ATTEMPTS = int(os.getenv("NOTIFY_AFTER_FAILED_ATTEMPTS", "3"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
