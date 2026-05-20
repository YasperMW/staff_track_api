from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from timezone_config import get_current_time
from typing import Optional, List, Dict, Any
from models.db_models import User, Notification, NotificationPreference, UserFCMToken
from fcm_service import send_push_notification
from mail_service import email_service
import logging
import hashlib
import json

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for sending notifications based on user preferences with rate limiting and deduplication"""
    
    NOTIFICATION_CATEGORIES = {
        'requests': ['request_submitted', 'request_approved', 'request_denied', 'request_escalated'],
        'announcements': ['announcement', 'urgent_announcement', 'policy_announcement'],
        'policies': ['leave_policy_update', 'policy_change'],
        'security': ['geofence_violation', 'security_alert'],
        'reminders': ['holiday_reminder', 'deadline_reminder'],
        'system': ['system_update', 'maintenance', 'account_update']
    }
    
    # Rate limiting configuration (notifications per hour per user per type)
    RATE_LIMITS = {
        'requests': 10,           # Request-related notifications
        'announcements': 5,       # Announcement notifications
        'policies': 3,           # Policy change notifications
        'security': 20,          # Security alerts (higher limit for important alerts)
        'reminders': 5,          # Reminder notifications
        'system': 10             # System notifications
    }
    
    # Deduplication window in minutes
    DEDUPLICATION_WINDOWS = {
        'requests': 5,           # Don't send duplicate request notifications within 5 minutes
        'announcements': 60,     # Don't duplicate announcements within 1 hour
        'policies': 30,          # Don't duplicate policy changes within 30 minutes
        'security': 2,           # Security alerts dedup window (short for urgent alerts)
        'reminders': 15,         # Reminder dedup window
        'system': 10             # System notification dedup window
    }
    
    @staticmethod
    def get_category_from_notification_type(notification_type: str) -> str:
        """Determine category from notification type"""
        for category, types in NotificationService.NOTIFICATION_CATEGORIES.items():
            if notification_type in types:
                return category
        return 'system'  # Default category
    
    @staticmethod
    def generate_content_hash(title: str, message: str, user_id: str, notification_type: str) -> str:
        """Generate a hash for notification content to detect duplicates"""
        content = f"{title}|{message}|{user_id}|{notification_type}"
        return hashlib.md5(content.encode()).hexdigest()
    
    @staticmethod
    def is_rate_limited(db: Session, user_id: str, notification_type: str) -> tuple[bool, Optional[str]]:
        """Check if user has exceeded rate limit for this notification type"""
        try:
            category = NotificationService.get_category_from_notification_type(notification_type)
            rate_limit = NotificationService.RATE_LIMITS.get(category, 10)
            
            # Count notifications in the last hour for this user and type
            one_hour_ago = get_current_time() - timedelta(hours=1)
            count = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.type == notification_type,
                Notification.created_at >= one_hour_ago
            ).count()
            
            if count >= rate_limit:
                return True, f"Rate limit exceeded: {count}/{rate_limit} notifications per hour for {notification_type}"
            
            return False, None
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return False, None
    
    @staticmethod
    def is_duplicate(db: Session, user_id: str, title: str, message: str, notification_type: str) -> tuple[bool, Optional[str]]:
        """Check if this is a duplicate notification within the deduplication window"""
        try:
            category = NotificationService.get_category_from_notification_type(notification_type)
            dedup_window = NotificationService.DEDUPLICATION_WINDOWS.get(category, 10)
            
            # Generate content hash
            content_hash = NotificationService.generate_content_hash(title, message, user_id, notification_type)
            
            # Check for similar notifications within the deduplication window
            window_start = get_current_time() - timedelta(minutes=dedup_window)
            
            # Look for notifications with same content hash or similar content
            similar_notifications = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.type == notification_type,
                Notification.created_at >= window_start
            ).all()
            
            for notification in similar_notifications:
                # Check exact content match
                existing_hash = NotificationService.generate_content_hash(
                    notification.title, notification.message, user_id, notification_type
                )
                if existing_hash == content_hash:
                    return True, f"Duplicate notification detected (content hash: {content_hash[:8]}...)"
                
                # Check for very similar content (90% similarity threshold)
                if NotificationService.calculate_similarity(title, message, notification.title, notification.message) > 0.9:
                    return True, f"Similar notification detected (similarity > 90%)"
            
            return False, None
        except Exception as e:
            logger.error(f"Error checking duplicate notification: {e}")
            return False, None
    
    @staticmethod
    def calculate_similarity(title1: str, message1: str, title2: str, message2: str) -> float:
        """Calculate similarity between two notifications (0.0 to 1.0)"""
        try:
            # Simple similarity calculation based on common words
            text1 = f"{title1} {message1}".lower().split()
            text2 = f"{title2} {message2}".lower().split()
            
            if not text1 or not text2:
                return 0.0
            
            set1 = set(text1)
            set2 = set(text2)
            
            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))
            
            return intersection / union if union > 0 else 0.0
        except Exception:
            return 0.0
    
    @staticmethod
    def get_user_preferences(db: Session, user_id: str) -> Dict[str, Dict[str, bool]]:
        """Get all notification preferences for a user"""
        preferences = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id
        ).all()
        
        pref_dict = {}
        for pref in preferences:
            pref_dict[pref.category] = {
                'email_enabled': pref.email_enabled,
                'push_enabled': pref.push_enabled,
                'in_app_enabled': pref.in_app_enabled
            }
        
        # Set default preferences for missing categories
        for category in NotificationService.NOTIFICATION_CATEGORIES.keys():
            if category not in pref_dict:
                pref_dict[category] = {
                    'email_enabled': True,
                    'push_enabled': True,
                    'in_app_enabled': True
                }
        
        return pref_dict
    
    @staticmethod
    def create_default_preferences(db: Session, user_id: str):
        """Create default notification preferences for a new user"""
        for category in NotificationService.NOTIFICATION_CATEGORIES.keys():
            existing = db.query(NotificationPreference).filter(
                NotificationPreference.user_id == user_id,
                NotificationPreference.category == category
            ).first()
            
            if not existing:
                preference = NotificationPreference(
                    user_id=user_id,
                    category=category,
                    email_enabled=True,
                    push_enabled=True,
                    in_app_enabled=True,
                    created_at=get_current_time(),
                    updated_at=get_current_time()
                )
                db.add(preference)
        
        db.commit()
    
    @staticmethod
    async def send_notification(
        db: Session,
        user_id: str,
        title: str,
        message: str,
        notification_type: str,
        data: Optional[Dict[str, Any]] = None,
        email_data: Optional[Dict[str, Any]] = None,
        force_send: bool = False  # Override rate limiting and deduplication
    ):
        """Send notification based on user preferences with rate limiting and deduplication"""
        try:
            # Check rate limiting (unless forced)
            if not force_send:
                is_rate_limited, rate_limit_reason = NotificationService.is_rate_limited(db, user_id, notification_type)
                if is_rate_limited:
                    logger.info(f"Notification rate limited for user {user_id}: {rate_limit_reason}")
                    return {"status": "rate_limited", "reason": rate_limit_reason}
                
                # Check for duplicates
                is_duplicate, duplicate_reason = NotificationService.is_duplicate(db, user_id, title, message, notification_type)
                if is_duplicate:
                    logger.info(f"Duplicate notification prevented for user {user_id}: {duplicate_reason}")
                    return {"status": "duplicate", "reason": duplicate_reason}
            
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                logger.warning(f"User {user_id} not found for notification")
                return {"status": "error", "reason": "User not found"}
            
            # Get user preferences
            preferences = NotificationService.get_user_preferences(db, user_id)
            category = NotificationService.get_category_from_notification_type(notification_type)
            user_prefs = preferences.get(category, {
                'email_enabled': True,
                'push_enabled': True,
                'in_app_enabled': True
            })
            
            notifications_sent = []
            
            # Send in-app notification
            if user_prefs['in_app_enabled']:
                notification = Notification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    type=notification_type,
                    is_read=False,
                    created_at=get_current_time(),
                    updated_at=get_current_time()
                )
                db.add(notification)
                db.commit()
                notifications_sent.append("in_app")
                logger.info(f"In-app notification sent to user {user_id}")
            
            # Send push notification
            if user_prefs['push_enabled']:
                fcm_tokens = db.query(UserFCMToken).filter(
                    UserFCMToken.user_id == user_id
                ).all()
                
                if fcm_tokens:
                    logger.info(f"🔔 PREPARING TO SEND PUSH NOTIFICATION")
                    logger.info(f"   User ID: {user_id}")
                    logger.info(f"   User: {user.first_name} {user.surname}")
                    logger.info(f"   Title: {title}")
                    logger.info(f"   Message: {message}")
                    logger.info(f"   Type: {notification_type}")
                    logger.info(f"   FCM Tokens Found: {len(fcm_tokens)}")
                    
                    # Add navigation data to the push notification
                    navigation_data = NotificationService._get_navigation_data(notification_type, data)
                    push_data = {**(data or {}), **navigation_data}
                    
                    for token_record in fcm_tokens:
                        try:
                            logger.info(f"📱 SENDING PUSH NOTIFICATION")
                            logger.info(f"   Token: {token_record.fcm_token[:20]}...")
                            logger.info(f"   To: {user.first_name} {user.surname}")
                            logger.info(f"   Title: {title}")
                            logger.info(f"   Message: {message}")
                            logger.info(f"   Type: {notification_type}")
                            logger.info(f"   Data: {push_data}")

                            response = await send_push_notification(
                                token=token_record.fcm_token,
                                title=title,
                                body=message,
                                data=push_data,
                                priority="high",
                                notification_type=notification_type
                            )

                            if response:
                                logger.info(f"✅ PUSH NOTIFICATION SENT SUCCESSFULLY")
                                logger.info(f"   Response: {response}")
                                notifications_sent.append("push")
                            else:
                                logger.error(f"❌ PUSH NOTIFICATION FAILED")
                                logger.error(f"   Token: {token_record.fcm_token[:20]}...")
                                logger.error(f"   User: {user.first_name} {user.surname}")
                                logger.error(f"   Title: {title}")
                                logger.error(f"   Message: {message}")
                                logger.error(f"   Data: {push_data}")
                        except Exception as e:
                            logger.error(f"❌ PUSH NOTIFICATION EXCEPTION")
                            logger.error(f"   Token: {token_record.fcm_token[:20]}...")
                            logger.error(f"   User: {user.first_name} {user.surname}")
                            logger.error(f"   Title: {title}")
                            logger.error(f"   Message: {message}")
                            logger.error(f"   Data: {push_data}")
                            logger.error(f"   Error: {e}")
                else:
                    logger.warning(f"⚠️  NO FCM TOKENS FOUND FOR USER {user_id}")
                    logger.warning(f"   User: {user.first_name} {user.surname}")
                    logger.warning(f"   Cannot send push notification without FCM tokens")
            
            # Send email notification
            if user_prefs['email_enabled'] and user.email and email_data:
                try:
                    await NotificationService._send_email_notification(
                        user.email,
                        f"{user.first_name} {user.surname}",
                        notification_type,
                        email_data
                    )
                    notifications_sent.append("email")
                    logger.info(f"Email notification sent to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send email notification: {e}")
            
            return {
                "status": "success",
                "notifications_sent": notifications_sent,
                "user_id": user_id,
                "notification_type": notification_type
            }
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return {"status": "error", "reason": str(e)}
    
    @staticmethod
    async def _send_email_notification(email: str, recipient_name: str, notification_type: str, email_data: Dict[str, Any]):
        """Send email notification based on type"""
        if notification_type == 'request_submitted':
            await email_service.send_request_submitted_email(
                email=email,
                approver_name=recipient_name,
                requester_name=email_data.get('requester_name', ''),
                request_type=email_data.get('request_type', ''),
                start_date=email_data.get('start_date', ''),
                end_date=email_data.get('end_date')
            )
        elif notification_type == 'request_approved':
            await email_service.send_request_approved_email(
                email=email,
                requester_name=recipient_name,
                request_type=email_data.get('request_type', ''),
                start_date=email_data.get('start_date', ''),
                end_date=email_data.get('end_date'),
                approver_name=email_data.get('approver_name'),
                comment=email_data.get('comment')
            )
        elif notification_type == 'request_denied':
            await email_service.send_request_denied_email(
                email=email,
                requester_name=recipient_name,
                request_type=email_data.get('request_type', ''),
                start_date=email_data.get('start_date', ''),
                end_date=email_data.get('end_date'),
                denied_by=email_data.get('denied_by'),
                denied_by_role=email_data.get('denied_by_role'),
                denied_at_level=email_data.get('denied_at_level', 1),
                comment=email_data.get('comment')
            )
        elif notification_type == 'geofence_violation':
            await email_service.send_geofence_violation_email(
                employee_email=email,
                employee_name=recipient_name,
                supervisor_email=email_data.get('supervisor_email', ''),
                supervisor_name=email_data.get('supervisor_name', ''),
                location=email_data.get('location', ''),
                distance_outside=email_data.get('distance_outside', 0),
                check_in_time=email_data.get('check_in_time', '')
            )
        elif notification_type in ['urgent_announcement', 'policy_announcement']:
            await email_service.send_announcement_email(
                email=email,
                recipient_name=recipient_name,
                announcement_title=email_data.get('title', ''),
                announcement_message=email_data.get('message', ''),
                announcement_type=email_data.get('type', ''),
                target_audience=email_data.get('target_audience', ''),
                author_name=email_data.get('author_name')
            )
        elif notification_type == 'leave_policy_update':
            await email_service.send_leave_policy_applied_email(
                email=email,
                employee_name=recipient_name,
                leave_type=email_data.get('leave_type', ''),
                allocated_days=email_data.get('allocated_days', 0),
                bonus_days=email_data.get('bonus_days', 0),
                total_available=email_data.get('total_available'),
                applied_by=email_data.get('applied_by'),
                target_role=email_data.get('target_role'),
                target_department=email_data.get('target_department')
            )
        else:
            logger.warning(f"Unknown notification type for email: {notification_type}")
    
    @staticmethod
    def update_user_preference(
        db: Session,
        user_id: str,
        category: str,
        email_enabled: Optional[bool] = None,
        push_enabled: Optional[bool] = None,
        in_app_enabled: Optional[bool] = None
    ):
        """Update user notification preference"""
        preference = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category
        ).first()
        
        if not preference:
            preference = NotificationPreference(
                user_id=user_id,
                category=category,
                email_enabled=email_enabled if email_enabled is not None else True,
                push_enabled=push_enabled if push_enabled is not None else True,
                in_app_enabled=in_app_enabled if in_app_enabled is not None else True,
                created_at=get_current_time(),
                updated_at=get_current_time()
            )
            db.add(preference)
        else:
            if email_enabled is not None:
                preference.email_enabled = email_enabled
            if push_enabled is not None:
                preference.push_enabled = push_enabled
            if in_app_enabled is not None:
                preference.in_app_enabled = in_app_enabled
            preference.updated_at = get_current_time()
        
        db.commit()
        logger.info(f"Updated notification preference for user {user_id}, category {category}")
    
    @staticmethod
    def _get_navigation_data(notification_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Generate navigation data based on notification type"""
        navigation_data = {"type": notification_type}
        
        if notification_type in ['attendance_reminder', 'check_in_reminder', 'check_out_reminder']:
            navigation_data["screen"] = "check_in_out"
        elif notification_type in ['request_submitted', 'request_approved', 'request_denied', 'request_escalated']:
            navigation_data["screen"] = "requests"
        elif notification_type in ['announcement', 'urgent_announcement', 'policy_announcement']:
            navigation_data["screen"] = "announcements"
        elif notification_type in ['geofence_violation', 'security_alert']:
            navigation_data["screen"] = "attendance"
        elif notification_type in ['leave_policy_update', 'policy_change']:
            navigation_data["screen"] = "announcements"
        elif notification_type in ['system_update', 'maintenance', 'account_update']:
            navigation_data["screen"] = "notifications"
        else:
            navigation_data["screen"] = "notifications"
        
        # Add any additional IDs from the data
        if data:
            if "request_id" in data:
                navigation_data["id"] = data["request_id"]
            elif "announcement_id" in data:
                navigation_data["id"] = data["announcement_id"]
            elif "attendance_id" in data:
                navigation_data["id"] = data["attendance_id"]
        
        return navigation_data

    @staticmethod
    def get_notification_stats(db: Session, user_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get notification statistics for a user"""
        try:
            start_time = get_current_time() - timedelta(hours=hours)
            
            notifications = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.created_at >= start_time
            ).all()
            
            stats = {
                'total_notifications': len(notifications),
                'by_type': {},
                'by_hour': {},
                'unread_count': 0
            }
            
            for notification in notifications:
                # Count by type
                notification_type = notification.type
                stats['by_type'][notification_type] = stats['by_type'].get(notification_type, 0) + 1
                
                # Count by hour
                hour = notification.created_at.hour
                stats['by_hour'][hour] = stats['by_hour'].get(hour, 0) + 1
                
                # Count unread
                if not notification.is_read:
                    stats['unread_count'] += 1
            
            return stats
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return {}

notification_service = NotificationService()
