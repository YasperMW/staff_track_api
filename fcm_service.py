import firebase_admin
from firebase_admin import credentials, messaging
import os
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
# You should place your service account key file in the root of the api directory
# and set the FIREBASE_SERVICE_ACCOUNT_PATH environment variable
service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")

try:
    if os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
    else:
        logger.warning(f"Firebase service account key not found at {service_account_path}. FCM will not work.")
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
