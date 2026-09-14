"""
Contact form API endpoint for PrimeData.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field


from ..services.email_service import send_contact_email

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/contact", tags=["Contact"])


class ContactFormRequest(BaseModel):
    """Contact form submission request model."""
    
    name: str = Field(..., min_length=1, max_length=255, description="User's name")
    email: EmailStr = Field(..., description="User's email address")
    feedback: str = Field(..., min_length=1, description="Feedback or query message")


class ContactFormResponse(BaseModel):
    """Contact form submission response model."""
    
    success: bool
    message: str


@router.post("/submit", response_model=ContactFormResponse)
async def submit_contact_form(request: ContactFormRequest):
    """
    Submit contact form.

    Sends an email to the configured feedback recipient (SMTP_TO_EMAIL or SMTP_USERNAME)
    with the user's name, email, and feedback.
    This endpoint is public (no authentication required) to allow anyone to contact us.
    """
    logger.info(f"📧 Contact form submission | name={request.name}, email={request.email}")

    try:
        # Send email using the email service
        logger.info(f"📋 Sending contact email | recipient={request.email}")
        success = send_contact_email(
            user_name=request.name,
            user_email=request.email,
            feedback=request.feedback
        )

        if success:
            logger.info(f"✅ Contact form submitted successfully | email={request.email}, name={request.name}")
            return ContactFormResponse(
                success=True,
                message="Thank you for contacting us! We'll get back to you soon."
            )
        else:
            # Email sending failed (likely SMTP not configured)
            logger.error(f"❌ Failed to send contact form email | email={request.email}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email service is currently unavailable. Please try again later or contact us directly."
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error processing contact form | email={request.email}, error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request. Please try again later."
        )

