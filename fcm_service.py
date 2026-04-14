import firebase_admin
from firebase_admin import credentials, messaging
import os
from typing import List, Optional, Dict, Any
import logging
import asyncio
from firebase_admin.exceptions import FirebaseError

logger = logging.getLogger(__name__)

# Mock response class for when Firebase is not initialized
class MockMulticastResponse:
    def __init__(self, success_count=0, failure_count=0):
        self.success_count = success_count
        self.failure_count = failure_count
        self.responses = []

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
        logger.info(f"Using Firebase credentials from environment for project: {project_id}")
        return credentials.Certificate(cred_dict)
    else:
        # Fall back to file-based approach
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
        if os.path.exists(service_account_path):
            logger.info(f"Using Firebase credentials from file: {service_account_path}")
            return credentials.Certificate(service_account_path)
        else:
            logger.warning("Firebase credentials not found. Please set FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY, FIREBASE_CLIENT_EMAIL environment variables or provide serviceAccountKey.json file")
            return None

# Global variable to track Firebase initialization status
_firebase_initialized = False

try:
    cred = get_firebase_credentials()
    if cred:
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase Admin SDK initialized successfully")
    else:
        logger.error("Firebase credentials not found. FCM will not work.")
except Exception as e:
    logger.error(f"Error initializing Firebase Admin SDK: {e}")
    _firebase_initialized = False


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
            visibility="public",
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
    if not _firebase_initialized:
        logger.error("Firebase not initialized. Cannot send push notification.")
        return None
        
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


async def send_fcm_push_enhanced(
    token: str, 
    title: str, 
    body: str, 
    data: Optional[dict] = None,
    priority: str = "high",
    notification_type: str = None
) -> Dict[str, Any]:
    """
    Enhanced FCM sending function with better error handling and response tracking.
    Based on the logic from other_app_notification.py.
    
    Args:
        token: The FCM registration token of the target device
        title: Notification title
        body: Notification body
        data: Optional data payload
        priority: Priority level (high/normal)
        notification_type: Type of notification for routing
        
    Returns:
        Dict containing the message ID or error information
    """
    if not token:
        raise ValueError("Token cannot be empty")
    
    if not _firebase_initialized:
        logger.error("Firebase not initialized. Cannot send push notification.")
        return {"success": False, "error": "Firebase not initialized", "status": "Failed to send message"}
        
    # Add priority and type to data payload
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
        token=token,
        data={k: str(v) for k, v in notification_data.items()},
        android=_get_android_config(priority, notification_type),
        apns=_get_apns_config(priority),
    )
    
    try:
        # Run blocking Firebase call in a thread executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, messaging.send, message)
        logger.info(f"Successfully sent message: {response}")
        return {"success": True, "message_id": response, "status": "Message sent successfully"}
    except ValueError as e:
        logger.error(f"Invalid argument error: {e}")
        return {"success": False, "error": f"Invalid argument: {str(e)}", "status": "Failed to send message"}
    except FirebaseError as e:
        logger.error(f"Firebase error: {e}")
        return {"success": False, "error": f"Firebase error: {str(e)}", "status": "Failed to send message"}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"success": False, "error": f"Unexpected error: {str(e)}", "status": "Failed to send message"}


async def send_multicast_push_notification(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    priority: str = "high",
    notification_type: str = None
):
    """Send a push notification to multiple devices with instant delivery settings"""
    if not _firebase_initialized:
        logger.error("Firebase not initialized. Cannot send multicast push notification.")
        # Return mock response to allow system to continue gracefully
        return MockMulticastResponse(success_count=0, failure_count=len(tokens) if tokens else 0)
        
    if not tokens:
        return MockMulticastResponse(success_count=0, failure_count=0)

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
        return MockMulticastResponse(success_count=0, failure_count=len(tokens))


async def test_fcm_connectivity():
    """Test Firebase FCM connectivity and return diagnostic information"""
    if not _firebase_initialized:
        return {
            "status": "error",
            "message": "Firebase not initialized",
            "suggestion": "Check Firebase credentials configuration"
        }
    
    try:
        # Test with a dummy message to a fake token
        # This will fail with "invalid registration token" but confirms connectivity
        test_message = messaging.Message(
            notification=messaging.Notification(
                title="Connectivity Test",
                body="This is a connectivity test",
            ),
            data={"test": "connectivity"},
            token="connectivity_test_token_12345",
        )
        
        # This should raise an exception about invalid token, which confirms connectivity
        messaging.send(test_message)
        
    except Exception as e:
        error_str = str(e).lower()
        
        if "registration token is not a valid" in error_str:
            return {
                "status": "success",
                "message": "FCM connectivity confirmed",
                "details": "Received expected 'invalid token' error, confirming connection to Firebase servers"
            }
        elif "remote end closed connection" in error_str or "connection" in error_str:
            return {
                "status": "error",
                "message": "Network connectivity issue",
                "details": f"Cannot connect to Firebase servers: {e}",
                "suggestion": "Check network connectivity, firewall settings, and proxy configuration"
            }
        elif "404" in error_str or "not found" in error_str:
            return {
                "status": "error", 
                "message": "Firebase endpoint not found (404)",
                "details": f"Firebase API endpoint returned 404: {e}",
                "suggestion": "Check Firebase project configuration and service account permissions"
            }
        else:
            return {
                "status": "error",
                "message": "Unexpected FCM error",
                "details": f"Unexpected error: {e}",
                "suggestion": "Check Firebase project settings and service account configuration"
            }
    
    return {
        "status": "unexpected",
        "message": "Unexpected success in connectivity test",
        "suggestion": "This should not happen - check the test logic"
    }
