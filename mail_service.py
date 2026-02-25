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
 
    def otp_expiry(self) -> datetime:
        """Return the expiry datetime for a new OTP code."""

        return datetime.utcnow() + timedelta(minutes=self.otp_expiry_minutes)


email_service = EmailService()