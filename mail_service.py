import os
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException, status
import resend


logger = logging.getLogger(__name__)


class EmailService:
    """Reusable service for sending all Staff Track emails."""

    def build_email_html(self, subject: str, body_html: str) -> str:
        """Universal branded wrapper for all Staff Track HTML emails."""

        return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;">
        <tr>
            <td align="center" style="padding:32px 0 16px;">
                <div style="font-size:32px;font-weight:700;color:#167c80;margin-bottom:8px;">Staff Track</div>
                <div style="font-size:14px;color:#64748b;">St. John's Hospital HR Management</div>
            </td>
        </tr>
        <tr>
            <td align="center">
                <table width="100%" style="max-width:520px;background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,0.08);" cellpadding="0" cellspacing="0">
                    <tr><td style="padding:44px 36px;">{body_html}</td></tr>
                </table>
            </td>
        </tr>
        <tr>
            <td align="center" style="padding:20px 0 0;">
                <div style="font-size:13px;color:#94a3b8;line-height:1.5;">St. John's Hospital<br>© {datetime.now().year} St. John's Hospital. All rights reserved.<br><span style="font-size:12px;color:#b2bac6;">This is an automated message — please do not reply.</span>
                </div>
            </td>
        </tr>
    </table>
</body>
</html>
'''
    def __init__(self) -> None:
        self.resend_api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
        self.mail_from_name = os.getenv("MAIL_FROM_NAME", "")
        self.otp_expiry_minutes = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))
        # Initialize Resend client
        if self.resend_api_key:
            resend.api_key = self.resend_api_key

    async def send_account_verification_email(self, email: str, otp_code: str) -> None:
        """Send account verification email"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        title = "Verify Your Staff Track Account"
        message = "Enter this code to complete your Staff Track account registration and start using the system."
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">
    {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    {message}
</p>
<div style="background-color: #f1f5f9; padding: 24px; border-radius: 12px; margin: 36px 0; border: 2px dashed #cbd5e1;">
    <div style="font-size: 38px; font-weight: bold; letter-spacing: 10px; color: #1e40af; font-family: 'Courier New', monospace;">
        {otp_code}
    </div>
</div>
<p style="font-size: 16px; color: #4b5563; margin: 0 0 32px;">
    This verification code expires in <strong>{self.otp_expiry_minutes} minutes</strong>.
</p>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">
        🎉 Welcome to Staff Track! We're excited to have you join our team.
    </p>
    <p style="font-size: 14px; color: #94a3b8; margin: 16px 0 0;">
        Didn't request this account? You can safely ignore this email.
    </p>
    <p style="font-size: 14px; color: #94a3b8; margin: 16px 0 0;">
        Never share this code — our team will never ask for it.
    </p>
</div>
'''
        subject = "Verify Your Staff Track Account"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Account verification email sent to {email}")
        except Exception as exc:  # pragma: no cover - network/Resend
            logger.error("Failed to send account verification email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email",
            ) from exc

    async def send_password_reset_otp_email(self, email: str, otp_code: str) -> None:
        """Send password reset OTP email"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        title = "Reset Your Staff Track Password"
        message = "Enter this code to reset your Staff Track account password and regain access to your account."
        
        body_html = f'''
<h1 style="font-size: 28px; color: #dc2626; margin: 0 0 24px; font-weight: 600;">
    {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    {message}
</p>
<div style="background-color: #fef2f2; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #dc2626;">
    <div style="font-size: 38px; font-weight: bold; letter-spacing: 10px; color: #dc2626; font-family: 'Courier New', monospace;">
        {otp_code}
    </div>
</div>
<p style="font-size: 16px; color: #4b5563; margin: 0 0 32px;">
    This reset code expires in <strong>{self.otp_expiry_minutes} minutes</strong>.
</p>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #991b1b; line-height: 1.6; margin: 0; font-weight: 500;">
        🔒 Security Notice
    </p>
    <p style="font-size: 14px; color: #991b1b; margin: 8px 0 0; line-height: 1.5;">
        If you did not request this password reset, please secure your account immediately and contact our support team.
    </p>
    <p style="font-size: 14px; color: #94a3b8; margin: 16px 0 0;">
        Never share this code — our team will never ask for it.
    </p>
</div>
'''
        subject = "Reset Your Staff Track Password"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Password reset OTP email sent to {email}")
        except Exception as exc:  # pragma: no cover - network/Resend
            logger.error("Failed to send password reset email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send password reset email",
            ) from exc

    async def send_otp_email(self, email: str, otp_code: str, purpose: str = "verification") -> None:
        """Legacy method - use specific methods instead"""
        if purpose == "password_reset":
            await self.send_password_reset_otp_email(email, otp_code)
        else:
            await self.send_account_verification_email(email, otp_code)

    async def send_welcome_email(self, email: str, first_name: str, user_type: str = "staff") -> None:
        """Send welcome email to new users after successful account creation"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Different content based on user type
        if user_type == "admin":
            subject = "Welcome to Staff Track - Administrator!"
            title = "Welcome to Staff Track - Administrator!"
            message = f"Hi {first_name},<br><br>Welcome to Staff Track! Your administrator account has been successfully created. You can now manage staff attendance, oversee system operations, and access comprehensive administrative features."
        elif user_type == "hr":
            subject = "Welcome to Staff Track - HR Manager!"
            title = "Welcome to Staff Track - HR Manager!"
            message = f"Hi {first_name},<br><br>Welcome to Staff Track! Your HR manager account has been successfully created. You can now manage employee records, handle attendance reports, and oversee human resources operations."
        else:
            subject = "Welcome to Staff Track!"
            title = "Welcome to Staff Track!"
            message = f"Hi {first_name},<br><br>Welcome to Staff Track! Your account has been successfully created. You can now check in/out, view your attendance history, and manage your work schedule all in one place."
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">{title}</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">{message}</p>
<div style="background-color: #f1f5f9; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #167c80;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Getting Started</h3>
    <p style="font-size: 14px; color: #4b5563; line-height: 1.6; margin: 0;">
        {"Access the admin dashboard to manage staff and system settings" if user_type == "admin" else "Manage employee records and attendance reports" if user_type == "hr" else "Start tracking your attendance and managing your work schedule"}.
    </p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">Need help? contact our support team <a href='mailto:hr@stjohnshospital.com'>hr@stjohnshospital.com</a>.</p>
</div>
'''
        html_body = self.build_email_html(subject, body_html)
        
        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Welcome email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send welcome email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send welcome email",
            ) from exc
        
    async def send_profile_update_email(self, email: str, first_name: str) -> None:
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        body_html = f'''
<h1 style="font-size: 24px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">Hi {first_name},</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">Your Staff Track profile was updated successfully.<br>If you did not make this change, please contact support immediately.</p>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">Need help? contact our support team <a href='mailto:hr@stjohnshospital.com'>hr@stjohnshospital.com</a>.</p>
</div>
'''
        html_body = self.build_email_html('Your Staff Track Profile Was Updated', body_html)
        
        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": "Your Staff Track Profile Was Updated",
                "html": html_body
            }
            
            resend.Emails.send(params)
        except Exception as exc:
            logger.error("Failed to send profile update email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send profile update email",
            ) from exc
    
    async def send_request_submitted_email(
        self, 
        email: str, 
        approver_name: str, 
        requester_name: str, 
        request_type: str, 
        start_date: str, 
        end_date: str = None
    ) -> None:
        """Send email to approver when a new request is submitted"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Format date range
        if end_date and end_date != start_date:
            date_range = f"{start_date} to {end_date}"
        else:
            date_range = start_date
        
        title = "New Request Submitted for Approval"
        message = f"{requester_name} has submitted a {request_type} request for {date_range} and requires your approval."
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">
    {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {approver_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    {message}
</p>
<div style="background-color: #f1f5f9; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #167c80;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Request Details</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Requester:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{requester_name}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Request Type:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{request_type.title()}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Period:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{date_range}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Status:</td>
            <td style="padding: 8px 0; color: #6b7280;">Pending Approval</td>
        </tr>
    </table>
</div>
<div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; border-radius: 6px; margin: 32px 0; text-align: left;">
    <p style="font-size: 14px; color: #92400e; margin: 0; font-weight: 500;">⏰ Action Required</p>
    <p style="font-size: 14px; color: #92400e; margin: 8px 0 0; line-height: 1.5;">Please review this request in your Staff Track dashboard and take appropriate action.</p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated notification from Staff Track. Please log in to your dashboard to review and respond to this request.</p>
</div>
'''
        subject = f"New {request_type.title()} Request - {requester_name}"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Request submitted email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send request submitted email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send request notification",
            ) from exc

    async def send_request_approved_email(
        self, 
        email: str, 
        requester_name: str, 
        request_type: str, 
        start_date: str, 
        end_date: str = None,
        approver_name: str = None,
        comment: str = None,
        is_final_approval: bool = True,
        approval_level: int = 1,
        next_approver_name: str = None
    ) -> None:
        """Send email to requester when their request is approved"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Format date range
        if end_date and end_date != start_date:
            date_range = f"{start_date} to {end_date}"
        else:
            date_range = start_date
        
        # Determine title and status based on approval progress
        if is_final_approval:
            title = "Your Request Has Been Fully Approved"
            status_html = '<td style="padding: 8px 0; color: #059669; font-weight: 600;">✅ Fully Approved</td>'
        else:
            title = "Update on Your Request"
            status_html = f'<td style="padding: 8px 0; color: #d97706; font-weight: 600;">⏳ Pending {next_approver_name or "Next Approver"} Approval</td>'
        
        # Additional message for partial approval
        if is_final_approval:
            message = f"Good news! Your {request_type} request for {date_range} has been <strong>fully approved</strong>!"
            footer_note = "All approval levels have completed. Your request is now confirmed."
        else:
            message = f"Your {request_type} request for {date_range} has been <strong>approved</strong> by {approver_name} and is now pending {next_approver_name or 'the next approver'}'s approval."
            footer_note = f"Approval Progress: Level {approval_level} of 4 complete. You'll receive another notification when the next approval is given."
        
        body_html = f'''
<h1 style="font-size: 28px; color: #059669; margin: 0 0 24px; font-weight: 600;">
    🎉 {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {requester_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    {message}
</p>
<div style="background-color: #ecfdf5; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #059669;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Request Details</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Request Type:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{request_type.title()}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Period:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{date_range}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Status:</td>
            {status_html}
        </tr>
    </table>
</div>
'''
        # Add approval progress note
        if not is_final_approval:
            body_html += f'''
<div style="background-color: #fef3c7; padding: 16px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #d97706;">
    <p style="font-size: 14px; color: #92400e; margin: 0; line-height: 1.5;">
        <strong>⏳ Approval in Progress:</strong> Your request has been approved at level {approval_level}. {footer_note}
    </p>
</div>
'''
        else:
            body_html += f'''
<div style="background-color: #ecfdf5; padding: 16px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #059669;">
    <p style="font-size: 14px; color: #065f46; margin: 0; line-height: 1.5;">
        <strong>✅ Complete:</strong> {footer_note}
    </p>
</div>
'''

        # Add approver comment if provided
        if comment:
            body_html += f'''
<div style="background-color: #f3f4f6; padding: 16px; border-radius: 8px; margin: 24px 0;">
    <h4 style="font-size: 14px; color: #374151; margin: 0 0 8px; font-weight: 600;">Approver's Comment:</h4>
    <p style="font-size: 14px; color: #6b7280; margin: 0; line-height: 1.5;">{comment}</p>
</div>
'''
        
        # Add approver name if provided
        if approver_name:
            body_html += f'''
<p style="font-size: 14px; color: #6b7280; margin: 24px 0 0;">
    Approved by: <strong>{approver_name}</strong>
</p>
'''
        
        body_html += '''
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated notification from Staff Track. Please keep this for your records.</p>
</div>
'''
        subject = f"Request Approved - {request_type.title()}"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Request approved email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send request approved email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send approval notification",
            ) from exc

    async def send_request_denied_email(
        self, 
        email: str, 
        requester_name: str, 
        request_type: str, 
        start_date: str, 
        end_date: str = None,
        denied_by: str = None,
        denied_by_role: str = None,
        denied_at_level: int = 1,
        comment: str = None
    ) -> None:
        """Send email to requester when their request is denied"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Format date range
        if end_date and end_date != start_date:
            date_range = f"{start_date} to {end_date}"
        else:
            date_range = start_date
        
        title = "Your Request Has Been Denied"
        
        # Denied by info
        denied_by_info = f"{denied_by}" if denied_by else "An approver"
        denied_role_info = f" ({denied_by_role})" if denied_by_role else ""
        
        body_html = f'''
<h1 style="font-size: 28px; color: #dc2626; margin: 0 0 24px; font-weight: 600;">
    ❌ {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {requester_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Your {request_type} request for {date_range} has been <strong>denied</strong> by {denied_by_info}{denied_role_info}.
</p>
<div style="background-color: #fef2f2; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #dc2626;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Request Details</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Request Type:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{request_type.title()}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Period:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{date_range}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Status:</td>
            <td style="padding: 8px 0; color: #dc2626; font-weight: 600;">❌ Denied</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Denied By:</td>
            <td style="padding: 8px 0; color: #6b7280;">{denied_by_info}{denied_role_info}</td>
        </tr>
    </table>
</div>
'''
        # Add approval level info
        body_html += f'''
<div style="background-color: #fef2f2; padding: 16px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #dc2626;">
    <p style="font-size: 14px; color: #991b1b; margin: 0; line-height: 1.5;">
        <strong>⛔ Denied at Approval Level {denied_at_level}:</strong> Your request reached {denied_at_level} of 4 approval levels before being denied. If you need to reapply, please contact the approver for feedback.
    </p>
</div>
'''
        
        # Add approver comment if provided
        if comment and comment.strip():
            body_html += f'''
<div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; border-radius: 6px; margin: 24px 0;">
    <h4 style="font-size: 14px; color: #92400e; margin: 0 0 8px; font-weight: 600;">Reason for Denial:</h4>
    <p style="font-size: 14px; color: #92400e; margin: 0; line-height: 1.5;">{comment}</p>
</div>
'''
        
        # Add approver name if provided
        if approver_name:
            body_html += f'''
<p style="font-size: 14px; color: #6b7280; margin: 24px 0 0;">
    Reviewed by: <strong>{approver_name}</strong>
</p>
'''
        
        body_html += '''
<div style="background-color: #f3f4f6; padding: 16px; border-radius: 8px; margin: 24px 0;">
    <p style="font-size: 14px; color: #374151; margin: 0; line-height: 1.5;">
        If you have questions about this decision or would like to discuss further, please contact your supervisor or the HR department.
    </p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated notification from Staff Track.</p>
</div>
'''
        subject = f"Request Denied - {request_type.title()}"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Request denied email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send request denied email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send denial notification",
            ) from exc

    async def send_request_reassigned_email(
        self, 
        email: str, 
        new_approver_name: str, 
        requester_name: str, 
        request_type: str, 
        start_date: str, 
        end_date: str = None,
        previous_approver_name: str = None
    ) -> None:
        """Send email to new approver when request is reassigned or escalated"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Format date range
        if end_date and end_date != start_date:
            date_range = f"{start_date} to {end_date}"
        else:
            date_range = start_date
        
        title = "Request Escalated for Your Approval"
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">
    📋 {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {new_approver_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    A {request_type} request from {requester_name} has been <strong>escalated</strong> to you for approval.
</p>
'''
        # Add previous approver info if provided
        if previous_approver_name:
            body_html += f'''
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    This request was previously reviewed by <strong>{previous_approver_name}</strong> and has now been escalated to your level.
</p>
'''
        
        body_html += f'''
<div style="background-color: #f1f5f9; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #167c80;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Request Details</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Requester:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{requester_name}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Request Type:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{request_type.title()}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Period:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{date_range}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Status:</td>
            <td style="padding: 8px 0; color: #6b7280;">Pending Your Approval</td>
        </tr>
    </table>
</div>
<div style="background-color: #dbeafe; border-left: 4px solid #2563eb; padding: 16px; border-radius: 6px; margin: 32px 0; text-align: left;">
    <p style="font-size: 14px; color: #1e3a8a; margin: 0; font-weight: 500;">📈 Escalated Request</p>
    <p style="font-size: 14px; color: #1e3a8a; margin: 8px 0 0; line-height: 1.5;">This request requires your attention as it has been escalated through the approval chain.</p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated notification from Staff Track. Please log in to your dashboard to review and respond to this escalated request.</p>
</div>
'''
        subject = f"Escalated {request_type.title()} Request - {requester_name}"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Request reassigned email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send request reassigned email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send reassignment notification",
            ) from exc

    async def send_geofence_violation_email(
        self, 
        employee_email: str, 
        employee_name: str, 
        supervisor_email: str, 
        supervisor_name: str,
        location: str,
        distance_outside: float,
        check_in_time: str
    ) -> None:
        """Send email notification for geofence violation to employee and supervisor"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Email to employee
        employee_subject = "⚠️ Geofence Violation Alert - Check-in Outside Allowed Area"
        employee_body_html = f'''
<h1 style="font-size: 28px; color: #dc2626; margin: 0 0 24px; font-weight: 600;">
    ⚠️ Geofence Violation Detected
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {employee_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Your recent check-in at <strong>{check_in_time}</strong> was detected <strong>{distance_outside:.0f} meters</strong> outside the designated work area.
</p>
<div style="background-color: #fef2f2; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #dc2626;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Violation Details</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Check-in Time:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{check_in_time}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Location:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{location}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Distance from Office:</td>
            <td style="padding: 8px 0; color: #dc2626; font-weight: 600;">{distance_outside:.0f} meters outside</td>
        </tr>
    </table>
</div>
<div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; border-radius: 6px; margin: 32px 0;">
    <p style="font-size: 14px; color: #92400e; margin: 0; font-weight: 500;">⚠️ Action Required</p>
    <p style="font-size: 14px; color: #92400e; margin: 8px 0 0; line-height: 1.5;">Please ensure you are within the designated work area for check-ins. Contact your supervisor if you believe this is an error.</p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated security alert from Staff Track. Your supervisor has been notified.</p>
</div>
'''
        
        # Email to supervisor
        supervisor_subject = f"🚨 Geofence Violation - {employee_name}"
        supervisor_body_html = f'''
<h1 style="font-size: 28px; color: #dc2626; margin: 0 0 24px; font-weight: 600;">
    🚨 Team Member Geofence Violation
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {supervisor_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    <strong>{employee_name}</strong> has checked in <strong>{distance_outside:.0f} meters</strong> outside the designated work area.
</p>
<div style="background-color: #fef2f2; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #dc2626;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Violation Details</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Employee:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{employee_name}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Check-in Time:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{check_in_time}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Location:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{location}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Distance from Office:</td>
            <td style="padding: 8px 0; color: #dc2626; font-weight: 600;">{distance_outside:.0f} meters outside</td>
        </tr>
    </table>
</div>
<div style="background-color: #dbeafe; border-left: 4px solid #2563eb; padding: 16px; border-radius: 6px; margin: 32px 0;">
    <p style="font-size: 14px; color: #1e3a8a; margin: 0; font-weight: 500;">👁️ Supervisor Action</p>
    <p style="font-size: 14px; color: #1e3a8a; margin: 8px 0 0; line-height: 1.5;">Please review this violation and follow up with the employee if necessary. This may require investigation or disciplinary action.</p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated security alert from Staff Track. Please review your dashboard for more details.</p>
</div>
'''
        
        # Send emails
        try:
            # Send to employee
            employee_params = {
                "from": from_email,
                "to": [employee_email],
                "subject": employee_subject,
                "html": self.build_email_html(employee_subject, employee_body_html)
            }
            resend.Emails.send(employee_params)
            logger.info(f"Geofence violation email sent to employee {employee_email}")
            
            # Send to supervisor
            supervisor_params = {
                "from": from_email,
                "to": [supervisor_email],
                "subject": supervisor_subject,
                "html": self.build_email_html(supervisor_subject, supervisor_body_html)
            }
            resend.Emails.send(supervisor_params)
            logger.info(f"Geofence violation email sent to supervisor {supervisor_email}")
            
        except Exception as exc:
            logger.error("Failed to send geofence violation emails: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send geofence violation notification",
            ) from exc

    async def send_announcement_email(
        self, 
        email: str, 
        recipient_name: str, 
        announcement_title: str, 
        announcement_message: str,
        announcement_type: str,
        target_audience: str,
        author_name: str = None
    ) -> None:
        """Send email notification for announcements to target audience"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        # Different styling based on announcement type
        if announcement_type.lower() == "urgent":
            title_color = "#dc2626"
            icon = "🚨"
            bg_color = "#fef2f2"
            border_color = "#dc2626"
        elif announcement_type.lower() == "policy":
            title_color = "#1e40af"
            icon = "📋"
            bg_color = "#eff6ff"
            border_color = "#1e40af"
        else:
            title_color = "#059669"
            icon = "📢"
            bg_color = "#ecfdf5"
            border_color = "#059669"
        
        title = f"{icon} {announcement_type.title()} Announcement"
        
        body_html = f'''
<h1 style="font-size: 28px; color: {title_color}; margin: 0 0 24px; font-weight: 600;">
    {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {recipient_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Please review the following {announcement_type.lower()} announcement:
</p>
<div style="background-color: {bg_color}; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid {border_color};">
    <h3 style="font-size: 20px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">{announcement_title}</h3>
    <div style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0;">
        {announcement_message.replace(chr(10), '<br>')}
    </div>
</div>
'''
        # Add author info if provided
        if author_name:
            body_html += f'''
<p style="font-size: 14px; color: #6b7280; margin: 24px 0 0;">
    Sent by: <strong>{author_name}</strong>
</p>
'''
        
        # Add target audience info
        body_html += f'''
<p style="font-size: 14px; color: #6b7280; margin: 8px 0 0;">
    Audience: <strong>{target_audience}</strong>
</p>
'''
        
        # Add action based on type
        if announcement_type.lower() == "urgent":
            body_html += '''
<div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; border-radius: 6px; margin: 24px 0;">
    <p style="font-size: 14px; color: #92400e; margin: 0; font-weight: 500;">⚠️ Immediate Attention Required</p>
    <p style="font-size: 14px; color: #92400e; margin: 8px 0 0; line-height: 1.5;">This is an urgent announcement that requires your immediate attention and action.</p>
</div>
'''
        elif announcement_type.lower() == "policy":
            body_html += '''
<div style="background-color: #f3f4f6; padding: 16px; border-radius: 8px; margin: 24px 0;">
    <p style="font-size: 14px; color: #374151; margin: 0; line-height: 1.5;">
        Please review this policy update carefully and ensure compliance with the new guidelines.
    </p>
</div>
'''
        
        body_html += '''
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated announcement from Staff Track. Please contact your supervisor if you have any questions.</p>
</div>
'''
        subject = f"{announcement_type.title()}: {announcement_title}"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Announcement email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send announcement email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send announcement notification",
            ) from exc

    async def send_leave_policy_applied_email(
        self, 
        email: str, 
        employee_name: str, 
        leave_type: str, 
        allocated_days: int, 
        bonus_days: int = 0,
        total_available: int = None,
        applied_by: str = None,
        target_role: str = None,
        target_department: str = None
    ) -> None:
        """Send email notification when leave policy is applied to employee"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        total_days = total_available or (allocated_days + bonus_days)
        
        title = "📊 Leave Policy Update"
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1e40af; margin: 0 0 24px; font-weight: 600;">
    {title}
</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Hi {employee_name},
</p>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">
    Your leave policy has been updated. Here are your new leave entitlement details:
</p>
<div style="background-color: #eff6ff; padding: 24px; border-radius: 12px; margin: 36px 0; border-left: 4px solid #1e40af;">
    <h3 style="font-size: 18px; color: #1f2937; margin: 0 0 16px; font-weight: 600;">Updated Leave Entitlement</h3>
    <table style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151; width: 40%;">Leave Type:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{leave_type.title().replace('_', ' ')}</td>
        </tr>
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Allocated Days:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{allocated_days} days</td>
        </tr>
'''
        # Add bonus days if applicable
        if bonus_days > 0:
            body_html += f'''
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #374151;">Bonus Days:</td>
            <td style="padding: 8px 0; border-bottom: 1px solid #e2e8f0; color: #6b7280;">{bonus_days} days</td>
        </tr>
'''
        
        body_html += f'''
        <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #374151;">Total Available:</td>
            <td style="padding: 8px 0; color: #1e40af; font-weight: 600;">{total_days} days</td>
        </tr>
    </table>
</div>
'''
        
        # Add policy scope information
        scope_info = []
        if target_role:
            scope_info.append(f"Role: {target_role}")
        if target_department:
            scope_info.append(f"Department: {target_department}")
        
        if scope_info:
            body_html += f'''
<div style="background-color: #f3f4f6; padding: 16px; border-radius: 8px; margin: 24px 0;">
    <p style="font-size: 14px; color: #374151; margin: 0; line-height: 1.5;">
        <strong>Policy Scope:</strong> {", ".join(scope_info)}
    </p>
</div>
'''
        
        # Add applied by information
        if applied_by:
            body_html += f'''
<p style="font-size: 14px; color: #6b7280; margin: 24px 0 0;">
    Policy applied by: <strong>{applied_by}</strong>
</p>
'''
        
        body_html += '''
<div style="background-color: #ecfdf5; border-left: 4px solid #059669; padding: 16px; border-radius: 6px; margin: 24px 0;">
    <p style="font-size: 14px; color: #065f46; margin: 0; font-weight: 500;">💡 What This Means</p>
    <p style="font-size: 14px; color: #065f46; margin: 8px 0 0; line-height: 1.5;">
        You can now request up to {total_days} days of {leave_type.replace('_', ' ')} leave. You can view your leave balance and submit requests through the Staff Track app.
    </p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">This is an automated notification from Staff Track. Please contact HR if you have any questions about your leave entitlement.</p>
</div>
'''.format(total_days=total_days, leave_type=leave_type.replace('_', ' '))
        
        subject = f"Leave Policy Updated - {leave_type.title().replace('_', ' ')}"
        html_body = self.build_email_html(subject, body_html)

        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body
            }
            
            resend.Emails.send(params)
            logger.info(f"Leave policy email sent to {email}")
        except Exception as exc:
            logger.error("Failed to send leave policy email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send leave policy notification",
            ) from exc

    async def send_password_reset_email(self, email: str, first_name: str) -> None:
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">Password Changed Successfully</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">Hi {first_name},<br><br>Your Staff Track account password has been successfully changed. You can now log in with your new password.</p>
<div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 16px; border-radius: 6px; margin: 32px 0; text-align: left;">
    <p style="font-size: 14px; color: #7f1d1d; margin: 0; font-weight: 500;">🔒 Security Tip</p>
    <p style="font-size: 14px; color: #991b1b; margin: 8px 0 0; line-height: 1.5;">If you did not request this password change, please reset your password immediately and contact our support team.</p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">Need help? contact our support team <a href='mailto:hr@stjohnshospital.com'>hr@stjohnshospital.com</a>.</p>
</div>
'''
        html_body = self.build_email_html('Your Staff Track Password Has Been Changed', body_html)
        
        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": "Your Staff Track Password Has Been Changed",
                "html": html_body
            }
            
            resend.Emails.send(params)
        except Exception as exc:
            logger.error("Failed to send password reset email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send password reset email",
            ) from exc
 
    async def send_password_change_email(self, email: str, first_name: str) -> None:
        """Send password change confirmation email"""
        from_email = f"{self.mail_from_name} <{self.from_email}>" if self.mail_from_name else self.from_email
        
        body_html = f'''
<h1 style="font-size: 28px; color: #1f2937; margin: 0 0 24px; font-weight: 600;">Password Changed Successfully</h1>
<p style="font-size: 16px; color: #4b5563; line-height: 1.6; margin: 0 0 36px;">Hi {first_name},<br><br>Your Staff Track account password has been successfully changed. You can now log in with your new password.</p>
<div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 16px; border-radius: 6px; margin: 32px 0; text-align: left;">
    <p style="font-size: 14px; color: #7f1d1d; margin: 0; font-weight: 500;">🔒 Security Tip</p>
    <p style="font-size: 14px; color: #991b1b; margin: 8px 0 0; line-height: 1.5;">If you did not request this password change, please reset your password immediately and contact our support team.</p>
</div>
<div style="padding-top: 32px; border-top: 1px solid #e2e8f0; margin-top: 40px;">
    <p style="font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0;">Need help? contact our support team <a href='mailto:hr@stjohnshospital.com'>hr@stjohnshospital.com</a>.</p>
</div>
'''
        html_body = self.build_email_html('Your Staff Track Password Has Been Changed', body_html)
        
        try:
            params = {
                "from": from_email,
                "to": [email],
                "subject": "Your Staff Track Password Has Been Changed",
                "html": html_body
            }
            
            resend.Emails.send(params)
        except Exception as exc:
            logger.error("Failed to send password change email to %s: %s", email, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send password change email",
            ) from exc
 
    def otp_expiry(self) -> datetime:
        """Return the expiry datetime for a new OTP code."""

        return datetime.utcnow() + timedelta(minutes=self.otp_expiry_minutes)


email_service = EmailService()