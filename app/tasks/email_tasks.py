# ===== app/tasks/email_tasks.py =====
from typing import Optional
import logging

from app.config.celery_config import celery_app
from app.services.email.email_service import EmailService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def send_verification_email(
        self,
        email: str,
        token: str,
        user_name: Optional[str] = None
):
    """
    Send email verification link to user

    Args:
        email: User's email address
        token: Verification token
        user_name: User's full name (optional)
    """
    try:
        logger.info(f"Sending verification email to {email}")

        EmailService.send_verification_email(
            email=email,
            token=token,
            user_name=user_name
        )

        logger.info(f"Verification email sent successfully to {email}")
        return {"status": "success", "email": email}

    except Exception as exc:
        logger.error(f"Failed to send verification email to {email}: {exc}")

        # Retry with exponential backoff: 1min, 2min, 4min
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )


@celery_app.task(bind=True, max_retries=3)
def send_password_reset_email(
        self,
        email: str,
        token: str,
        user_name: Optional[str] = None
):
    """
    Send password reset link to user

    Args:
        email: User's email address
        token: Password reset token
        user_name: User's full name (optional)
    """
    try:
        logger.info(f"Sending password reset email to {email}")

        EmailService.send_password_reset_email(
            email=email,
            token=token,
            user_name=user_name
        )

        logger.info(f"Password reset email sent successfully to {email}")
        return {"status": "success", "email": email}

    except Exception as exc:
        logger.error(f"Failed to send password reset email to {email}: {exc}")

        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )


@celery_app.task(bind=True, max_retries=3)
def send_business_invite_email(
        self,
        email: str,
        business_name: str,
        invite_token: str,
        role: str,
        inviter_name: Optional[str] = None
):
    """
    Send business invitation email

    Args:
        email: Invitee's email address
        business_name: Name of the business
        invite_token: Invitation token
        role: Role in the business (owner/member)
        inviter_name: Name of person who sent the invite (optional)
    """
    try:
        logger.info(f"Sending business invite email to {email} for {business_name}")

        EmailService.send_business_invite_email(
            email=email,
            business_name=business_name,
            invite_token=invite_token,
            role=role,
            inviter_name=inviter_name
        )

        logger.info(f"Business invite email sent successfully to {email}")
        return {"status": "success", "email": email, "business": business_name}

    except Exception as exc:
        logger.error(f"Failed to send business invite email to {email}: {exc}")

        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )


@celery_app.task(bind=True, max_retries=3)
def send_platform_invite_email(
        self,
        email: str,
        invite_token: str,
        inviter_name: Optional[str] = None
):
    """
    Send platform invitation email

    Args:
        email: Invitee's email address
        invite_token: Invitation token
        inviter_name: Name of person who sent the invite (optional)
    """
    try:
        logger.info(f"Sending platform invite email to {email}")

        EmailService.send_platform_invite_email(
            email=email,
            invite_token=invite_token,
            inviter_name=inviter_name
        )

        logger.info(f"Platform invite email sent successfully to {email}")
        return {"status": "success", "email": email}

    except Exception as exc:
        logger.error(f"Failed to send platform invite email to {email}: {exc}")

        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )


@celery_app.task(bind=True, max_retries=3)
def send_appointment_confirmation_email(
        self,
        email: str,
        customer_name: str,
        appointment_datetime: str,
        service_type: str,
        business_name: str,
        duration_minutes: int,
        location: Optional[str] = None,
        notes: Optional[str] = None
):
    """
    Send appointment confirmation email to customer

    Args:
        email: Customer's email address
        customer_name: Customer's name
        appointment_datetime: Appointment date/time (formatted string)
        service_type: Type of service
        business_name: Name of the business
        duration_minutes: Appointment duration
        location: Business location (optional)
        notes: Additional notes (optional)
    """
    try:
        logger.info(f"Sending appointment confirmation email to {email}")

        # Build appointment details HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">Appointment Confirmed!</h1>
            </div>

            <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">Hi {customer_name},</h2>

                <p style="font-size: 16px; color: #555;">
                    Your appointment with <strong>{business_name}</strong> has been confirmed!
                </p>

                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 25px 0;">
                    <h3 style="margin-top: 0; color: #333; font-size: 18px;">Appointment Details</h3>

                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Service:</td>
                            <td style="padding: 8px 0; color: #333;">{service_type}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Date & Time:</td>
                            <td style="padding: 8px 0; color: #333;">{appointment_datetime}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Duration:</td>
                            <td style="padding: 8px 0; color: #333;">{duration_minutes} minutes</td>
                        </tr>
                        {f'''<tr>
                            <td style="padding: 8px 0; color: #666; font-weight: bold;">Location:</td>
                            <td style="padding: 8px 0; color: #333;">{location}</td>
                        </tr>''' if location else ''}
                    </table>

                    {f'''<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e0e0e0;">
                        <p style="margin: 0; color: #666;"><strong>Notes:</strong></p>
                        <p style="margin: 5px 0 0 0; color: #333;">{notes}</p>
                    </div>''' if notes else ''}
                </div>

                <p style="font-size: 14px; color: #555;">
                    We look forward to seeing you! If you need to reschedule or cancel, 
                    please contact us as soon as possible.
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; margin: 0;">
                    This is an automated confirmation. Please don't reply to this email.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; font-size: 12px; color: #999;">
                <p>© 2024 {business_name}. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
        Appointment Confirmed!

        Hi {customer_name},

        Your appointment with {business_name} has been confirmed!

        Appointment Details:
        - Service: {service_type}
        - Date & Time: {appointment_datetime}
        - Duration: {duration_minutes} minutes
        {f'- Location: {location}' if location else ''}

        {f'Notes: {notes}' if notes else ''}

        We look forward to seeing you! If you need to reschedule or cancel, 
        please contact us as soon as possible.

        © 2024 {business_name}. All rights reserved.
        """

        EmailService.send_email(
            to_email=email,
            subject=f"Appointment Confirmed - {business_name}",
            html_content=html_content,
            plain_text=plain_text
        )

        logger.info(f"Appointment confirmation email sent successfully to {email}")
        return {"status": "success", "email": email}

    except Exception as exc:
        logger.error(f"Failed to send appointment confirmation email to {email}: {exc}")

        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )


@celery_app.task(bind=True, max_retries=3)
def send_appointment_reminder_email(
        self,
        email: str,
        customer_name: str,
        appointment_datetime: str,
        service_type: str,
        business_name: str,
        location: Optional[str] = None
):
    """
    Send appointment reminder email to customer

    Args:
        email: Customer's email address
        customer_name: Customer's name
        appointment_datetime: Appointment date/time (formatted string)
        service_type: Type of service
        business_name: Name of the business
        location: Business location (optional)
    """
    try:
        logger.info(f"Sending appointment reminder email to {email}")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">⏰ Appointment Reminder</h1>
            </div>

            <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">Hi {customer_name},</h2>

                <p style="font-size: 16px; color: #555;">
                    This is a friendly reminder about your upcoming appointment with <strong>{business_name}</strong>.
                </p>

                <div style="background-color: #fff3cd; padding: 20px; border-left: 4px solid #ffc107; border-radius: 4px; margin: 25px 0;">
                    <h3 style="margin-top: 0; color: #856404; font-size: 18px;">📅 Appointment Details</h3>

                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #856404; font-weight: bold;">Service:</td>
                            <td style="padding: 8px 0; color: #333;">{service_type}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #856404; font-weight: bold;">Date & Time:</td>
                            <td style="padding: 8px 0; color: #333;">{appointment_datetime}</td>
                        </tr>
                        {f'''<tr>
                            <td style="padding: 8px 0; color: #856404; font-weight: bold;">Location:</td>
                            <td style="padding: 8px 0; color: #333;">{location}</td>
                        </tr>''' if location else ''}
                    </table>
                </div>

                <p style="font-size: 14px; color: #555;">
                    We look forward to seeing you! If you need to reschedule or cancel, 
                    please contact us as soon as possible.
                </p>

                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; margin: 0;">
                    This is an automated reminder. Please don't reply to this email.
                </p>
            </div>

            <div style="text-align: center; padding: 20px; font-size: 12px; color: #999;">
                <p>© 2024 {business_name}. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
        Appointment Reminder

        Hi {customer_name},

        This is a friendly reminder about your upcoming appointment with {business_name}.

        Appointment Details:
        - Service: {service_type}
        - Date & Time: {appointment_datetime}
        {f'- Location: {location}' if location else ''}

        We look forward to seeing you! If you need to reschedule or cancel, 
        please contact us as soon as possible.

        © 2024 {business_name}. All rights reserved.
        """

        EmailService.send_email(
            to_email=email,
            subject=f"Reminder: Upcoming Appointment - {business_name}",
            html_content=html_content,
            plain_text=plain_text
        )

        logger.info(f"Appointment reminder email sent successfully to {email}")
        return {"status": "success", "email": email}

    except Exception as exc:
        logger.error(f"Failed to send appointment reminder email to {email}: {exc}")

        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )