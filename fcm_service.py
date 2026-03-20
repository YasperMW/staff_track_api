import firebase_admin
from firebase_admin import credentials, messaging
import os
from typing import List, Optional, Dict, Any
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


def _get_android_config(priority: str = "high", notification_type: str = None) -> messaging.AndroidConfig:
    """Get Android-specific configuration for instant delivery"""
    # Map notification types to priority channels
    urgent_types = [
        'check_in_reminder', 'check_out_reminder', 'attendance_reminder',
        'attendance_alert', 'urgent', 'urgent_request', 'geofence_violation'
    ]

    channel_id = "staff_track_urgent" if (notification_type and notification_type in urgent_types) else "staff_track_channel"

    return messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            channel_id=channel_id,
            priority="high",
            default_sound=True,
            default_vibrate_timings=True,
            default_light_settings=True,
            visibility=messaging.AndroidNotificationVisibility.PUBLIC,
        ),
        ttl=86400,  # 24 hours - messages should not expire quickly
    )


def _get_apns_config(priority: str = "high") -> messaging.APNSConfig:
    """Get iOS APNS configuration for instant delivery"""
    return messaging.APNSConfig(
        headers={
            "apns-priority": "10",  # 10 = high priority, immediate delivery
            "apns-push-type": "alert",  # Required for iOS 13+
        },
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                content_available=True,  # Required for background processing
                mutable_content=True,  # Allows notification extension to modify
                sound="default",
                badge=1,
            )
        )
    )


async def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    priority: str = "high",
    notification_type: str = None
):
    """Send a push notification to a single device with instant delivery settings"""
    try:
        # Add priority to data payload for client-side handling
        notification_data = data or {}
        if priority == "high":
            notification_data["priority"] = "urgent"
        if notification_type:
            notification_data["type"] = notification_type

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={k: str(v) for k, v in notification_data.items()},  # FCM data must be strings
            token=token,
            android=_get_android_config(priority, notification_type),
            apns=_get_apns_config(priority),
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
    data: Optional[Dict[str, Any]] = None,
    priority: str = "high",
    notification_type: str = None
):
    """Send a push notification to multiple devices with instant delivery settings"""
    if not tokens:
        return None

    # Add priority to data payload
    notification_data = data or {}
    if priority == "high":
        notification_data["priority"] = "urgent"
    if notification_type:
        notification_data["type"] = notification_type

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={k: str(v) for k, v in notification_data.items()},
            tokens=tokens,
            android=_get_android_config(priority, notification_type),
            apns=_get_apns_config(priority),
        )
        response = messaging.send_multicast(message)
        logger.info(f"Successfully sent multicast message: {response.success_count} successes, {response.failure_count} failures")

        # Log any failures for debugging
        if response.failure_count > 0:
            for i, resp in enumerate(response.responses):
                if not resp.success:
                    logger.error(f"Failed to send to token {tokens[i][:20]}...: {resp.exception}")

        return response
    except Exception as e:
        logger.error(f"Error sending multicast push notification: {e}")
        return None
