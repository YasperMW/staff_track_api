"""
Attendance Scheduler Service
Handles scheduled notifications for check-in reminders and check-out reminders
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_, text
from database import get_db
from models.db_models import User, UserFCMToken, Notification, AttendanceLog
from fcm_service import send_push_notification
from timezone_config import get_current_time, get_day_start, get_day_end

logger = logging.getLogger(__name__)

class AttendanceScheduler:
    """Service for scheduling attendance-related notifications"""
    
    @staticmethod
    async def send_check_in_reminders():
        """Send check-in reminders 30 minutes before day shift starts (7:00 AM for 7:30 AM shift)"""
        try:
            current_time = get_current_time()
            
            # Only run at 7:00 AM
            if current_time.hour != 7 or current_time.minute != 0:
                return
            
            logger.info("Running check-in reminders scheduler")
            
            # Get database session
            db = next(get_db())
            
            try:
                # Get all active users who haven't checked in today
                today_start = get_day_start(current_time)
                today_end = get_day_end(current_time)
                
                # Find users who haven't checked in today
                checked_in_user_ids = db.query(AttendanceLog.user_id).filter(
                    and_(
                        AttendanceLog.check_in_time >= today_start,
                        AttendanceLog.check_in_time <= today_end
                    )
                ).subquery()
                
                users_to_remind = db.query(User).filter(
                    and_(
                        User.deleted_at.is_(None),
                        ~User.user_id.in_(checked_in_user_ids)
                    )
                ).all()
                
                logger.info(f"Found {len(users_to_remind)} users who haven't checked in today")
                
                for user in users_to_remind:
                    await AttendanceScheduler._send_check_in_reminder(db, user)
                
                logger.info(f"Sent check-in reminders to {len(users_to_remind)} users")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in check-in reminders scheduler: {e}")
    
    @staticmethod
    async def send_check_out_reminders():
        """Send check-out reminders at 4:00 PM"""
        try:
            current_time = get_current_time()
            
            # Only run at 4:00 PM
            if current_time.hour != 16 or current_time.minute != 0:
                return
            
            logger.info("Running check-out reminders scheduler")
            
            # Get database session
            db = next(get_db())
            
            try:
                # Get all users who checked in but haven't checked out today
                today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                # Find users who checked in but haven't checked out
                users_to_remind = db.query(User).join(
                    AttendanceLog,
                    and_(
                        AttendanceLog.user_id == User.user_id,
                        AttendanceLog.check_in_time >= today_start,
                        AttendanceLog.check_in_time <= today_end,
                        AttendanceLog.check_out_time.is_(None)
                    )
                ).filter(User.deleted_at.is_(None)).all()
                
                logger.info(f"Found {len(users_to_remind)} users who haven't checked out today")
                
                for user in users_to_remind:
                    await AttendanceScheduler._send_check_out_reminder(db, user)
                
                logger.info(f"Sent check-out reminders to {len(users_to_remind)} users")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in check-out reminders scheduler: {e}")

    @staticmethod
    async def send_late_checkin_alerts():
        """Send alerts to users who haven't checked in by 9:00 AM (late check-in)"""
        try:
            current_time = get_current_time()

            # Only run at 9:00 AM
            if current_time.hour != 9 or current_time.minute != 0:
                return

            logger.info("Running late check-in alerts scheduler")

            # Get database session
            db = next(get_db())

            try:
                # Get all active users who haven't checked in today
                today_start = get_day_start(current_time)
                today_end = get_day_end(current_time)

                # Find users who haven't checked in yet
                checked_in_user_ids = db.query(AttendanceLog.user_id).filter(
                    and_(
                        AttendanceLog.check_in_time >= today_start,
                        AttendanceLog.check_in_time <= today_end
                    )
                ).subquery()

                late_users = db.query(User).filter(
                    and_(
                        User.deleted_at.is_(None),
                        ~User.user_id.in_(checked_in_user_ids)
                    )
                ).all()

                logger.info(f"Found {len(late_users)} users who are late for check-in")

                for user in late_users:
                    await AttendanceScheduler._send_late_checkin_alert(db, user)

                logger.info(f"Sent late check-in alerts to {len(late_users)} users")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error in late check-in alerts scheduler: {e}")
    
    @staticmethod
    async def _send_check_in_reminder(db: Session, user: User):
        """Send check-in reminder to a specific user"""
        try:
            # Get user's FCM tokens
            fcm_tokens = db.query(UserFCMToken).filter(UserFCMToken.user_id == user.user_id).all()
            
            if fcm_tokens:
                for token_record in fcm_tokens:
                    await send_push_notification(
                        token=token_record.fcm_token,
                        title="⏰ Check-in Reminder",
                        body="Good morning! Don't forget to check in for your day shift.",
                        data={
                            "type": "check_in_reminder",
                            "reminder_time": get_current_time().isoformat()
                        }
                    )
            
            # Create in-app notification
            notification = Notification(
                user_id=user.user_id,
                title="⏰ Check-in Reminder",
                message="Good morning! Don't forget to check in for your day shift.",
                type="reminder",
                is_read=False,
                created_at=get_current_time(),
                updated_at=get_current_time()
            )
            db.add(notification)
            db.commit()
            
            logger.info(f"Sent check-in reminder to user {user.user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send check-in reminder to user {user.user_id}: {e}")
    
    @staticmethod
    async def _send_check_out_reminder(db: Session, user: User):
        """Send check-out reminder to a specific user"""
        try:
            # Get today's attendance record for work hours calculation
            today_start = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            attendance = db.query(AttendanceLog).filter(
                and_(
                    AttendanceLog.user_id == user.user_id,
                    AttendanceLog.check_in_time >= today_start,
                    AttendanceLog.check_in_time <= today_end,
                    AttendanceLog.check_out_time.is_(None)
                )
            ).first()
            
            if not attendance:
                return
            
            # Calculate current work hours
            current_hours = (get_current_time() - attendance.check_in_time).total_seconds() / 3600.0
            
            # Get user's FCM tokens
            fcm_tokens = db.query(UserFCMToken).filter(UserFCMToken.user_id == user.user_id).all()
            
            if fcm_tokens:
                for token_record in fcm_tokens:
                    await send_push_notification(
                        token=token_record.fcm_token,
                        title="⏰ Check-out Reminder",
                        body=f"It's 4:00 PM! Time to check out. Current work hours: {current_hours:.1f}",
                        data={
                            "type": "check_out_reminder",
                            "current_hours": str(round(current_hours, 2)),
                            "reminder_time": get_current_time().isoformat()
                        }
                    )
            
            # Create in-app notification
            notification = Notification(
                user_id=user.user_id,
                title="⏰ Check-out Reminder",
                message=f"It's 4:00 PM! Time to check out. Current work hours: {current_hours:.1f}",
                type="reminder",
                is_read=False,
                created_at=get_current_time(),
                updated_at=get_current_time()
            )
            db.add(notification)
            db.commit()
            
            logger.info(f"Sent check-out reminder to user {user.user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send check-out reminder to user {user.user_id}: {e}")

    @staticmethod
    async def _send_late_checkin_alert(db: Session, user: User):
        """Send late check-in alert to a specific user"""
        try:
            # Get user's FCM tokens
            fcm_tokens = db.query(UserFCMToken).filter(UserFCMToken.user_id == user.user_id).all()

            if fcm_tokens:
                for token_record in fcm_tokens:
                    await send_push_notification(
                        token=token_record.fcm_token,
                        title="⚠️ Late Check-in Alert",
                        body="You haven't checked in yet. Please check in immediately or contact your supervisor.",
                        data={
                            "type": "late_checkin_alert",
                            "reminder_time": get_current_time().isoformat()
                        }
                    )

            # Create in-app notification
            notification = Notification(
                user_id=user.user_id,
                title="⚠️ Late Check-in Alert",
                message="You haven't checked in yet. Please check in immediately or contact your supervisor.",
                type="reminder",
                is_read=False,
                created_at=get_current_time(),
                updated_at=get_current_time()
            )
            db.add(notification)
            db.commit()

            logger.info(f"Sent late check-in alert to user {user.user_id}")

        except Exception as e:
            logger.error(f"Failed to send late check-in alert to user {user.user_id}: {e}")

# Global scheduler instance
attendance_scheduler = AttendanceScheduler()

# Scheduler tasks that can be called by a cron job or task scheduler
async def run_check_in_reminders():
    """Task to be called by scheduler at 7:30 AM daily"""
    await attendance_scheduler.send_check_in_reminders()

async def run_check_out_reminders():
    """Task to be called by scheduler at 4:00 PM daily"""
    await attendance_scheduler.send_check_out_reminders()

async def run_late_checkin_alerts():
    """Task to be called by scheduler at 9:00 AM daily"""
    await attendance_scheduler.send_late_checkin_alerts()

if __name__ == "__main__":
    # For testing purposes
    asyncio.run(run_check_in_reminders())
    asyncio.run(run_check_out_reminders())
    asyncio.run(run_late_checkin_alerts())
