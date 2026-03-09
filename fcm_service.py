import firebase_admin
from firebase_admin import credentials, messaging
import os
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
# You can either set FIREBASE_SERVICE_ACCOUNT_PATH to point to a JSON file
# or set individual environment variables for the credentials
def get_firebase_credentials():
    # Try environment variables first
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    private_key_id = os.getenv("FIREBASE_PRIVATE_KEY_ID")
    private_key = os.getenv("FIREBASE_PRIVATE_KEY")
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
    client_id = os.getenv("FIREBASE_CLIENT_ID")
    auth_uri = os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
    token_uri = os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token")
    
    if all([project_id, private_key_id, private_key, client_email, client_id]):
        # Use environment variables
        cred_dict = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": private_key_id,
            "private_key": private_key.replace("\\n", "\n"),
            "client_email": client_email,
            "client_id": client_id,
            "auth_uri": auth_uri,
            "token_uri": token_uri
        }
        return credentials.Certificate(cred_dict)
    else:
        # Fall back to file-based approach
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
        if os.path.exists(service_account_path):
            return credentials.Certificate(service_account_path)
        return None

try:
    cred = get_firebase_credentials()
    if cred:
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
    else:
        logger.warning("Firebase credentials not found. FCM will not work.")
except Exception as e:
    logger.error(f"Error initializing Firebase Admin SDK: {e}")

async def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None
):
    """Send a push notification to a single device"""
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
        )
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return response
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return None

async def send_multicast_push_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None
):
    """Send a push notification to multiple devices"""
    if not tokens:
        return None
        
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=tokens,
        )
        response = messaging.send_multicast(message)
        logger.info(f"Successfully sent multicast message: {response.success_count} successes, {response.failure_count} failures")
        return response
    except Exception as e:
        logger.error(f"Error sending multicast push notification: {e}")
        return None
