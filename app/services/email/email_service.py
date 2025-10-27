# ===== app/services/email/email_service.py =====
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import logging

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""

    @staticmethod
    def _get_smtp_connection():
        """Create and return SMTP connection"""
        try:
            if settings.EMAIL_USE_TLS:
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT)

            if settings.EMAIL_USERNAME and settings.EMAIL_PASSWORD:
                server.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)

            return server
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            raise

    @staticmethod
    def send_email(
            to_email: str,
            subject: str,
            html_content: str,
            plain_text: Optional[str] = None,
            cc: Optional[List[str]] = None,
            bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Send an email using SMTP

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            plain_text: Plain text version (fallback for non-HTML clients)
            cc: List of CC email addresses
            bcc: List of BCC email addresses

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
            msg['To'] = to_email

            if cc:
                msg['Cc'] = ', '.join(cc)

            # Attach plain text version
            if plain_text:
                part1 = MIMEText(plain_text, 'plain')
                msg.attach(part1)

            # Attach HTML version
            part2 = MIMEText(html_content, 'html')
            msg.attach(part2)

            # Prepare recipient list
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)

            # Send email
            server = EmailService._get_smtp_connection()
            server.sendmail(settings.EMAIL_FROM_ADDRESS, recipients, msg.as_string())
            server.quit()

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            raise

    @staticmethod
    def send_verification_email(email: str, token: str, user_name: Optional[str] = None) -> bool:
        """Send email verification link"""
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"

        display_name = user_name or "there"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">Verify Your Email</h1>
            </div>

            <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">Hi {display_name}!</h2>

                <p style="font-size: 16px; color: #555;">
                    Welcome to Voxio Desk! We're excited to have you on board.
                </p>

                <p style="font-size: 16px; color: #555;">
                    Please verify your email address by clicking the button below:
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_url}" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; 
                              padding: 14px 40px; 
                              text-decoration: none; 
                              border-radius: 5px; 
                              font-weight: bold;
                              display: inline-block;
                              font-size: 16px;">
                        Verify Email Address
                    </a>
                </div>

                <p style="font-size: 14px; color: #777; margin-top: 30px;">
                    Or copy and paste this link into your browser:
                </p>
                <p style="font-size: 14px; color: #667eea; word-break: break-all;">
                    {verification_url}
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; margin: 0;">
                    This verification link will expire in 24 hours. If you didn't create an account, 
                    you can safely ignore this email.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; font-size: 12px; color: #999;">
                <p>© 2025 VoxioDesk. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
        Hi {display_name}!

        Welcome to VoxioDesk! We're excited to have you on board.

        Please verify your email address by clicking the link below:
        {verification_url}

        This verification link will expire in 24 hours.

        If you didn't create an account, you can safely ignore this email.

        © 2025 VoxioDesk. All rights reserved.
        """

        return EmailService.send_email(
            to_email=email,
            subject="Verify Your Email Address",
            html_content=html_content,
            plain_text=plain_text
        )

    @staticmethod
    def send_password_reset_email(email: str, token: str, user_name: Optional[str] = None) -> bool:
        """Send password reset link"""
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

        display_name = user_name or "there"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">Reset Your Password</h1>
            </div>

            <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">Hi {display_name},</h2>

                <p style="font-size: 16px; color: #555;">
                    We received a request to reset your password. If you didn't make this request, 
                    you can safely ignore this email.
                </p>

                <p style="font-size: 16px; color: #555;">
                    To reset your password, click the button below:
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                              color: white; 
                              padding: 14px 40px; 
                              text-decoration: none; 
                              border-radius: 5px; 
                              font-weight: bold;
                              display: inline-block;
                              font-size: 16px;">
                        Reset Password
                    </a>
                </div>

                <p style="font-size: 14px; color: #777; margin-top: 30px;">
                    Or copy and paste this link into your browser:
                </p>
                <p style="font-size: 14px; color: #f5576c; word-break: break-all;">
                    {reset_url}
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; margin: 0;">
                    This password reset link will expire in 1 hour for security reasons. 
                    If you didn't request a password reset, please ignore this email or contact support 
                    if you have concerns.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; font-size: 12px; color: #999;">
                <p>© 2025 VoxioDesk. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
        Hi {display_name},

        We received a request to reset your password. If you didn't make this request, 
        you can safely ignore this email.

        To reset your password, click the link below:
        {reset_url}

        This password reset link will expire in 1 hour for security reasons.

        If you didn't request a password reset, please ignore this email or contact support 
        if you have concerns.

        © 2025 VoxioDesk. All rights reserved.
        """

        return EmailService.send_email(
            to_email=email,
            subject="Reset Your Password",
            html_content=html_content,
            plain_text=plain_text
        )

    @staticmethod
    def send_business_invite_email(
            email: str,
            business_name: str,
            invite_token: str,
            role: str,
            inviter_name: Optional[str] = None
    ) -> bool:
        """Send business invitation email"""
        register_url = f"{settings.FRONTEND_URL}/register?invite={invite_token}"

        inviter = inviter_name or "Someone"
        role_display = "an Owner" if role == "owner" else "a Member"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">You're Invited!</h1>
            </div>

            <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">Join {business_name}</h2>

                <p style="font-size: 16px; color: #555;">
                    {inviter} has invited you to join <strong>{business_name}</strong> as {role_display} 
                    on VoxioDesk.
                </p>

                <p style="font-size: 16px; color: #555;">
                    Click the button below to accept the invitation and create your account:
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{register_url}" 
                       style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                              color: white; 
                              padding: 14px 40px; 
                              text-decoration: none; 
                              border-radius: 5px; 
                              font-weight: bold;
                              display: inline-block;
                              font-size: 16px;">
                        Accept Invitation
                    </a>
                </div>

                <p style="font-size: 14px; color: #777; margin-top: 30px;">
                    Or copy and paste this link into your browser:
                </p>
                <p style="font-size: 14px; color: #4facfe; word-break: break-all;">
                    {register_url}
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; margin: 0;">
                    This invitation link will expire in 7 days. If you didn't expect this invitation, 
                    you can safely ignore this email.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; font-size: 12px; color: #999;">
                <p>© 2025 VoxioDesk. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
        You're Invited to Join {business_name}!

        {inviter} has invited you to join {business_name} as {role_display} on VoxioDesk.

        Click the link below to accept the invitation and create your account:
        {register_url}

        This invitation link will expire in 7 days.

        If you didn't expect this invitation, you can safely ignore this email.

        © 2025 VoxioDesk. All rights reserved.
        """

        return EmailService.send_email(
            to_email=email,
            subject=f"You're invited to join {business_name}",
            html_content=html_content,
            plain_text=plain_text
        )

    @staticmethod
    def send_platform_invite_email(email: str, invite_token: str, inviter_name: Optional[str] = None) -> bool:
        """Send platform invitation email"""
        register_url = f"{settings.FRONTEND_URL}/register?invite={invite_token}"

        inviter = inviter_name or "The VoxioDesk team"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">Welcome to VoxioDesk!</h1>
            </div>

            <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">You've Been Invited</h2>

                <p style="font-size: 16px; color: #555;">
                    {inviter} has invited you to join VoxioDesk, where you can manage your business 
                    appointments and scheduling with ease.
                </p>

                <p style="font-size: 16px; color: #555;">
                    Click the button below to create your account and get started:
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{register_url}" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; 
                              padding: 14px 40px; 
                              text-decoration: none; 
                              border-radius: 5px; 
                              font-weight: bold;
                              display: inline-block;
                              font-size: 16px;">
                        Create Account
                    </a>
                </div>

                <p style="font-size: 14px; color: #777; margin-top: 30px;">
                    Or copy and paste this link into your browser:
                </p>
                <p style="font-size: 14px; color: #667eea; word-break: break-all;">
                    {register_url}
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; margin: 0;">
                    This invitation link will expire in 7 days. If you didn't expect this invitation, 
                    you can safely ignore this email.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; font-size: 12px; color: #999;">
                <p>© 2025 VoxioDesk. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
        Welcome to VoxioDesk!

        {inviter} has invited you to join VoxioDesk, where you can manage your business 
        appointments and scheduling with ease.

        Click the link below to create your account and get started:
        {register_url}

        This invitation link will expire in 7 days.

        If you didn't expect this invitation, you can safely ignore this email.

        © 2025 VoxioDesk. All rights reserved.
        """

        return EmailService.send_email(
            to_email=email,
            subject="You're invited to join VoxioDesk",
            html_content=html_content,
            plain_text=plain_text
        )