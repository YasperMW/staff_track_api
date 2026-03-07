# Attendance Notifications System

This document describes the attendance notification system implemented for the Staff Track app.

## Features Implemented

### 1. Check-in/Check-out Confirmation Notifications
- **Check-in Confirmation**: Sent immediately after successful check-in
- **Check-out Confirmation**: Sent immediately after successful check-out
- Includes time, shift type, and work hours (for check-out)

### 2. Geofence Violation Notifications
- **Check-in Geofence**: Blocks check-in and notifies user + supervisor when outside work area
- **Check-out Geofence**: Blocks check-out and notifies user + supervisor when outside work area
- Both actions are refused with HTTP 400 error
- Includes distance outside of geofence
- Sends push notifications, in-app notifications, and emails

### 3. Scheduled Reminders
- **Check-in Reminders**: Sent at 7:00 AM daily (30 minutes before day shift)
- **Check-out Reminders**: Sent at 4:00 PM daily
- Only sent to users who haven't checked in/out yet

## Notification Types

### Push Notifications
- Sent via Firebase Cloud Messaging (FCM)
- Requires user to have FCM token registered
- Works in foreground, background, and terminated app states

### In-App Notifications
- Stored in database
- Visible in notifications screen
- Marked as read/unread

## Technical Implementation

### Files Modified/Created
1. `attendance_endpoints.py` - Added confirmation notifications
2. `attendance_scheduler.py` - New scheduler service
3. `main.py` - Integrated scheduler with startup event

### Scheduler Logic
- Runs every minute checking current time
- Only executes notifications at specific times (7:00 AM, 4:00 PM)
- Uses timezone-aware datetime (Africa/Blantyre)

### Database Integration
- Uses existing `Notification` model for in-app notifications
- Uses existing `UserFCMToken` model for push notifications
- Respects user notification preferences

## Testing

### Test Endpoint
```
POST /attendance/test-notifications
```
Parameters:
- `notification_type`: "check_in_reminder" or "check_out_reminder"

### Manual Testing
1. Check-in at any location → Should receive confirmation
2. Check-out → Should receive confirmation with work hours
3. Use test endpoint to verify reminders work

## Configuration

### Timezone
- Default: Africa/Blantyre
- Can be changed in `attendance_scheduler.py` and `attendance_endpoints.py`

### Schedule Times
- Check-in reminder: 7:00 AM (configurable)
- Check-out reminder: 4:00 PM (configurable)

## Notification Content

### Check-in Confirmation
- Title: "✅ Check-in Successful"
- Body: "Checked in at HH:MM • Shift Type"
- Data: attendance_log_id, check_in_time, shift_type

### Check-out Confirmation
- Title: "✅ Check-out Successful"
- Body: "Checked out at HH:MM • X.X hours worked"
- Data: attendance_log_id, check_out_time, work_hours, shift_type

### Check-in Geofence Violation
- Title: "⚠️ Geofence Violation"
- Body: "Your check-in was detected Xm outside the work area"
- Data: type, distance, location

### Check-out Geofence Violation
- Title: "⚠️ Geofence Violation"
- Body: "Your check-out was detected Xm outside the work area"
- Data: type, action: "check_out", distance, location

### Supervisor Geofence Alert
- Title: "🚨 Geofence Violation Alert"
- Body: "[Employee Name] checked in/out outside work area"
- Data: type, action, employee_id, employee_name, distance

### Check-in Reminder
- Title: "⏰ Check-in Reminder"
- Body: "Good morning! Don't forget to check in for your day shift."
- Data: reminder_time

### Check-out Reminder
- Title: "⏰ Check-out Reminder"
- Body: "It's 4:00 PM! Time to check out. Current work hours: X.X"
- Data: current_hours, reminder_time

## Troubleshooting

### Common Issues
1. **Notifications not sending**: Check FCM token registration
2. **Wrong time**: Verify timezone configuration
3. **Scheduler not running**: Check main.py startup event
4. **Database errors**: Check database connection and models

### Logging
- Scheduler logs to console and logger
- Error handling prevents crashes
- Failed notifications are logged but don't stop the system

## Summary

The attendance notification system now provides comprehensive coverage for:
- ✅ **Real-time confirmations** for check-in/check-out actions
- ✅ **Geofence monitoring** for both check-in and check-out locations
- ✅ **Scheduled reminders** to improve attendance compliance
- ✅ **Supervisor alerts** for policy violations

## Future Enhancements

### Potential Improvements
1. **Customizable reminder times** per user
2. **Different schedules** for different departments
3. **Weekend/holiday exceptions**
4. **Overtime alerts**
5. **Missed check-in alerts to supervisors**
6. **Weekly attendance summaries**

### Additional Notification Types
1. **Late check-in alerts**
2. **Early check-out warnings**
3. **Shift change notifications**
4. **Attendance goal achievements**
