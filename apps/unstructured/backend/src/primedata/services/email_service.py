"""
Email service for sending verification and notification emails.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from urllib.parse import quote

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

from primedata.core.settings import get_settings


def _connect_and_send(msg: MIMEMultipart) -> bool:
    """Open an SMTP connection and send a pre-built message.

    Handles TLS/SSL selection and optional authentication based on
    application settings. The connection is closed after sending.

    :param msg: Fully constructed MIMEMultipart message to send.
    :return: True if the message was sent successfully.
    :raises smtplib.SMTPException: On SMTP communication failure.
    """
    settings = get_settings()

    logger.debug(f"Connecting to SMTP server | host={settings.SMTP_HOST} | port={settings.SMTP_PORT}")
    if settings.SMTP_USE_TLS:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()
    elif settings.SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)

    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        logger.debug("Authenticating with SMTP server")
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

    server.send_message(msg)
    server.quit()
    return True


def send_verification_email(email: str, verification_token: str, user_name: str = None) -> bool:
    """Send an email verification link to a newly registered user.

    :param email: Recipient's email address.
    :param verification_token: Unique token embedded in the verification URL.
    :param user_name: Optional user's display name for email personalization.
    :return: True if the email was sent successfully, False otherwise.
    """
    logger.info(f"📧 send_verification_email ENTRY | email={email} | user_name={user_name} | token_len={len(verification_token)}")

    settings = get_settings()

    # Check if email is enabled
    if not settings.SMTP_ENABLED:
        logger.warning(f"📧 send_verification_email | SMTP is disabled, email not sent")
        return False

    try:
        # Get frontend URL for verification link
        logger.debug(f"📋 Building verification link")
        frontend_url = settings.FRONTEND_URL.rstrip('/')
        # URL-encode the token to handle special characters safely
        verification_link = f"{frontend_url}/verify-email?token={quote(verification_token)}"

        # Create message
        logger.debug(f"📋 Creating MIME message")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Verify your PrimeData account"
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = email
        
        # Email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 30px;
                    border-radius: 10px;
                    color: white;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    margin-top: 20px;
                    color: #333;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="margin: 0; color: white;">PrimeData</h1>
            </div>
            <div class="content">
                <h2>Verify your email address</h2>
                <p>Hello{f' {user_name}' if user_name else ''},</p>
                <p>Thank you for signing up for PrimeData! Please verify your email address by clicking the button below:</p>
                <p style="text-align: center;">
                    <a href="{verification_link}" class="button">Verify Email Address</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{verification_link}</p>
                <p>This link will expire in 24 hours.</p>
                <p>If you didn't create an account with PrimeData, please ignore this email.</p>
                <div class="footer">
                    <p></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
        Verify your PrimeData account

        Hello{f' {user_name}' if user_name else ''},

        Thank you for signing up for PrimeData! Please verify your email address by visiting:

        {verification_link}

        This link will expire in 24 hours.

        If you didn't create an account with PrimeData, please ignore this email.
        """

        # Attach parts
        logger.debug(f"📋 Attaching email body parts")
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        _connect_and_send(msg)

        logger.info(f"✅ send_verification_email | email={email} | success=True")
        return True

    except Exception as e:
        logger.error(f"❌ send_verification_email | email={email} | error={str(e)}", exc_info=True)
        return False


def send_password_reset_email(email: str, reset_token: str, user_name: str = None) -> bool:
    """Send a password reset link to the user.

    :param email: Recipient's email address.
    :param reset_token: Unique token embedded in the password reset URL.
    :param user_name: Optional user's display name for email personalization.
    :return: True if the email was sent successfully, False otherwise.
    """
    logger.info(f"📧 send_password_reset_email ENTRY | email={email} | user_name={user_name} | token_len={len(reset_token)}")

    settings = get_settings()

    if not settings.SMTP_ENABLED:
        logger.warning(f"📧 send_password_reset_email | SMTP is disabled, email not sent")
        return False

    try:
        logger.debug(f"📋 Building password reset link")
        frontend_url = settings.FRONTEND_URL.rstrip('/')
        # URL-encode the token to handle special characters safely
        reset_link = f"{frontend_url}/reset-password?token={quote(reset_token)}"

        logger.debug(f"📋 Creating MIME message")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Reset your PrimeData password"
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = email
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 30px;
                    border-radius: 10px;
                    color: white;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    margin-top: 20px;
                    color: #333;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="margin: 0; color: white;">PrimeData</h1>
            </div>
            <div class="content">
                <h2>Reset your password</h2>
                <p>Hello{f' {user_name}' if user_name else ''},</p>
                <p>You requested to reset your password. Click the button below to reset it:</p>
                <p style="text-align: center;">
                    <a href="{reset_link}" class="button">Reset Password</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{reset_link}</p>
                <p>This link will expire in 1 hour.</p>
                <p>If you didn't request a password reset, please ignore this email.</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Reset your PrimeData password

        Hello{f' {user_name}' if user_name else ''},

        You requested to reset your password. Visit:

        {reset_link}

        This link will expire in 1 hour.

        If you didn't request a password reset, please ignore this email.
        """

        logger.debug(f"📋 Attaching email body parts")
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        _connect_and_send(msg)

        logger.info(f"✅ send_password_reset_email | email={email} | success=True")
        return True

    except Exception as e:
        logger.error(f"❌ send_password_reset_email | email={email} | error={str(e)}", exc_info=True)
        return False


def send_contact_email(user_name: str, user_email: str, feedback: str) -> bool:
    """Send a contact form submission to the configured feedback email address.

    :param user_name: Name of the person submitting the form.
    :param user_email: Email address of the submitter (set as Reply-To).
    :param feedback: The feedback or query message body.
    :return: True if the email was sent successfully, False otherwise.
    """
    logger.info(f"📧 send_contact_email ENTRY | user_name={user_name} | user_email={user_email} | feedback_len={len(feedback)}")

    settings = get_settings()

    if not settings.SMTP_ENABLED:
        logger.warning(f"📧 send_contact_email | SMTP is disabled, email not sent")
        return False

    try:
        # Feedback recipient email - use SMTP_TO_EMAIL setting or fallback to SMTP_USERNAME
        # ⚠️ WARNING: Set SMTP_TO_EMAIL environment variable for production!
        logger.debug(f"📋 Determining feedback recipient email")
        from primedata.core.settings import get_settings
        settings = get_settings()
        feedback_email = settings.SMTP_TO_EMAIL or settings.SMTP_USERNAME
        if not feedback_email:
            logger.error(f"❌ send_contact_email | SMTP_TO_EMAIL or SMTP_USERNAME must be set for contact form submissions")
            return False

        logger.debug(f"📋 Creating contact form message | feedback_recipient={feedback_email}")
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Contact Form Submission from {user_name}"
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = feedback_email
        msg['Reply-To'] = user_email  # Set reply-to to user's email
        
        # Email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 30px;
                    border-radius: 10px;
                    color: white;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    margin-top: 20px;
                    color: #333;
                }}
                .info-box {{
                    background: #f5f5f5;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 15px 0;
                    border-left: 4px solid #667eea;
                }}
                .feedback-box {{
                    background: #f9f9f9;
                    padding: 20px;
                    border-radius: 5px;
                    margin: 15px 0;
                    border: 1px solid #e0e0e0;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="margin: 0; color: white;">PrimeData Contact Form</h1>
            </div>
            <div class="content">
                <h2>New Contact Form Submission</h2>
                
                <div class="info-box">
                    <p><strong>Name:</strong> {user_name}</p>
                    <p><strong>Email:</strong> <a href="mailto:{user_email}">{user_email}</a></p>
                </div>
                
                <h3>Message:</h3>
                <div class="feedback-box">
                    {feedback}
                </div>
                
                <div class="footer">
                    <p>This email was sent from the PrimeData contact form.</p>
                    <p>You can reply directly to this email to respond to {user_name}.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
        PrimeData Contact Form Submission

        Name: {user_name}
        Email: {user_email}

        Message:
        {feedback}

        ---
        This email was sent from the PrimeData contact form.
        You can reply directly to this email to respond to {user_name}.
        """

        # Attach parts
        logger.debug(f"📋 Attaching email body parts")
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        _connect_and_send(msg)

        logger.info(f"✅ send_contact_email | user_email={user_email} | feedback_recipient={feedback_email} | success=True")
        return True

    except Exception as e:
        logger.error(f"❌ send_contact_email | user_email={user_email} | error={str(e)}", exc_info=True)
        return False
