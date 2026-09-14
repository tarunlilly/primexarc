"""
Billing API endpoints for PrimeData.

This module provides endpoints for Stripe billing integration,
including checkout sessions, customer portal, and webhooks.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..core.plan_limits import get_plan_limits, get_plan_limit
from ..core.security import get_current_user
from ..db.database import get_db
from ..db.models import BillingPlan, BillingProfile, DataSource, PipelineRun, Product, RawFile, Workspace

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

router = APIRouter()


class CheckoutSessionRequest(BaseModel):
    """Request model for creating checkout session."""

    workspace_id: str
    plan: str  # "pro" or "enterprise"


class CheckoutSessionResponse(BaseModel):
    """Response model for checkout session."""

    checkout_url: str
    session_id: str


class BillingLimitsResponse(BaseModel):
    """Response model for billing limits."""

    plan: str
    limits: Dict[str, Any]
    usage: Dict[str, Any]


class BillingPortalResponse(BaseModel):
    """Response model for billing portal."""

    portal_url: str


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Create a Stripe checkout session for plan upgrade.

    Args:
        request: Checkout session request with workspace and plan
        db: Database session
        current_user: Current authenticated user

    Returns:
        Checkout session URL and ID
    """
    logger.info(f"💳 Creating checkout session | workspace_id={request.workspace_id}, plan={request.plan}")

    # Check if Stripe is configured
    if not stripe.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="🚀 You're in beta! We've unlocked all premium features for free so you can fully explore and test the platform. Go ahead and try any plan - no credit card needed. Payment options will be available soon."
        )

    try:
        # Get workspace
        workspace = db.query(Workspace).filter(Workspace.id == request.workspace_id).first()
        if not workspace:
            logger.warning(f"💳 Workspace not found | workspace_id={request.workspace_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        # Get or create billing profile
        billing_profile = db.query(BillingProfile).filter(BillingProfile.workspace_id == request.workspace_id).first()

        if not billing_profile:
            logger.info(f"📋 Creating billing profile | workspace_id={request.workspace_id}")
            billing_profile = BillingProfile(workspace_id=request.workspace_id, plan=BillingPlan.ENTERPRISE)
            db.add(billing_profile)
            db.commit()

        # Create Stripe customer if not exists
        if not billing_profile.stripe_customer_id:
            logger.info(f"💳 Creating Stripe customer | workspace={workspace.name}")
            customer = stripe.Customer.create(
                email=current_user.get("email", ""), name=workspace.name, metadata={"workspace_id": str(workspace.id)}
            )
            billing_profile.stripe_customer_id = customer.id
            db.commit()
            logger.info(f"✅ Stripe customer created | customer_id={customer.id}")

        # Define plan pricing
        plan_prices = {
            "pro": "price_1234567890",  # Replace with actual Stripe price ID
            "enterprise": "price_0987654321",  # Replace with actual Stripe price ID
        }

        if request.plan not in plan_prices:
            logger.warning(f"❌ Invalid plan | plan={request.plan}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan")

        # Create checkout session
        logger.info(f"📋 Creating Stripe checkout session | customer_id={billing_profile.stripe_customer_id}, plan={request.plan}")
        session = stripe.checkout.Session.create(
            customer=billing_profile.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": plan_prices[request.plan],
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/app/billing?success=true",
            cancel_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/app/billing?canceled=true",
            metadata={"workspace_id": str(workspace.id), "plan": request.plan},
        )
        logger.info(f"✅ Checkout session created | session_id={session.id}")

        return CheckoutSessionResponse(checkout_url=session.url, session_id=session.id)

    except stripe.error.StripeError as e:
        # Check if it's an API key error
        if "No API key provided" in str(e) or "api_key" in str(e).lower():
            logger.error(f"❌ Stripe API key error | error={str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="🚀 You're in beta! We've unlocked all premium features for free so you can fully explore and test the platform. Go ahead and try any plan - no credit card needed. Payment options will be available soon."
            )
        logger.error(f"❌ Stripe error | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Checkout session creation failed | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create checkout session: {str(e)}")


@router.get("/portal", response_model=BillingPortalResponse)
async def get_customer_portal(
    workspace_id: str, db: Session = Depends(get_db)
):
    """
    Get Stripe customer portal URL.

    Args:
        workspace_id: Workspace ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Customer portal URL
    """
    logger.info(f"💳 Getting customer portal | workspace_id={workspace_id}")

    # Check if Stripe is configured
    if not stripe.api_key:
        logger.warning(f"💳 Stripe not configured | workspace_id={workspace_id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="🚀 You're in beta! We've unlocked all premium features for free so you can fully explore and test the platform. Go ahead and try any plan - no credit card needed. Payment options will be available soon."
        )

    try:
        # Get billing profile
        billing_profile = db.query(BillingProfile).filter(BillingProfile.workspace_id == workspace_id).first()

        if not billing_profile or not billing_profile.stripe_customer_id:
            logger.warning(f"💳 Billing profile not found | workspace_id={workspace_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No billing profile found")

        # Create portal session
        logger.info(f"📋 Creating portal session | customer_id={billing_profile.stripe_customer_id}")
        portal_session = stripe.billing_portal.Session.create(
            customer=billing_profile.stripe_customer_id,
            return_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/app/billing",
        )
        logger.info(f"✅ Portal session created | session_url={portal_session.url}")

        return BillingPortalResponse(portal_url=portal_session.url)

    except stripe.error.StripeError as e:
        # Check if it's an API key error
        if "No API key provided" in str(e) or "api_key" in str(e).lower():
            logger.error(f"❌ Stripe API key error | error={str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="🚀 You're in beta! We've unlocked all premium features for free so you can fully explore and test the platform. Go ahead and try any plan - no credit card needed. Payment options will be available soon."
            )
        logger.error(f"❌ Stripe error | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Portal session creation failed | workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create portal session: {str(e)}")


@router.get("/limits", response_model=BillingLimitsResponse)
async def get_billing_limits(workspace_id: str, db: Session = Depends(get_db)):
    """
    Get billing limits and usage for workspace.

    Args:
        workspace_id: Workspace ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Billing limits and current usage
    """
    logger.info(f"💳 Fetching billing limits | workspace_id={workspace_id}")

    try:
        # Get billing profile
        billing_profile = db.query(BillingProfile).filter(BillingProfile.workspace_id == workspace_id).first()

        if not billing_profile:
            logger.info(f"📋 Creating default billing profile | workspace_id={workspace_id}")
            # Create default billing profile
            billing_profile = BillingProfile(workspace_id=workspace_id, plan=BillingPlan.ENTERPRISE)
            db.add(billing_profile)
            db.commit()

        # Get plan limits from central configuration
        current_plan = (
            billing_profile.plan.value.lower() if hasattr(billing_profile.plan, "value") else str(billing_profile.plan).lower()
        )
        plan_limits_dict = get_plan_limits(current_plan)

        # Build limits response (exclude internal fields like schedule_frequency)
        limits = {
            "max_products": plan_limits_dict.get("max_products", -1),
            "max_data_sources_per_product": plan_limits_dict.get("max_data_sources_per_product", -1),
            "max_pipeline_runs_per_month": plan_limits_dict.get("max_pipeline_runs_per_month", -1),
            "max_raw_files_size_mb": plan_limits_dict.get("max_raw_files_size_mb", -1),
        }

        # Calculate actual usage
        usage = calculate_workspace_usage(workspace_id, db)
        logger.info(f"✅ Billing limits retrieved | plan={current_plan}, usage={usage}")

        return BillingLimitsResponse(plan=current_plan, limits=limits, usage=usage)

    except Exception as e:
        logger.error(f"❌ Failed to get billing limits | workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get billing limits: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhooks for subscription changes.

    Args:
        request: FastAPI request object

    Returns:
        Success response
    """
    logger.info(f"📋 Processing Stripe webhook")

    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")

        if not webhook_secret:
            logger.error(f"❌ Webhook secret not configured", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook secret not configured")

        # Verify webhook signature
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        logger.info(f"📋 Webhook event verified | event_type={event['type']}")

        # Handle different event types
        if event["type"] == "customer.subscription.created":
            logger.info(f"✅ Processing subscription created event")
            await handle_subscription_created(event)
        elif event["type"] == "customer.subscription.updated":
            logger.info(f"✅ Processing subscription updated event")
            await handle_subscription_updated(event)
        elif event["type"] == "customer.subscription.deleted":
            logger.info(f"✅ Processing subscription deleted event")
            await handle_subscription_deleted(event)

        logger.info(f"✅ Webhook processed successfully")
        return {"status": "success"}

    except stripe.error.SignatureVerificationError:
        logger.error(f"❌ Invalid webhook signature", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    except Exception as e:
        logger.error(f"❌ Webhook processing error | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Webhook error: {str(e)}")


async def handle_subscription_created(event: Dict[str, Any]):
    """Handle subscription created event."""
    # Implementation for subscription created
    pass


async def handle_subscription_updated(event: Dict[str, Any]):
    """Handle subscription updated event."""
    # Implementation for subscription updated
    pass


async def handle_subscription_deleted(event: Dict[str, Any]):
    """Handle subscription deleted event."""
    # Implementation for subscription deleted
    pass


def calculate_workspace_usage(workspace_id: str, db: Session) -> Dict[str, Any]:
    """
    Calculate actual usage for a workspace.

    Args:
        workspace_id: Workspace ID (string or UUID)
        db: Database session

    Returns:
        Dictionary with usage metrics
    """
    logger.info(f"📊 Calculating workspace usage | workspace_id={workspace_id}")

    workspace_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

    # Count products
    products_count = db.query(func.count(Product.id)).filter(Product.workspace_id == workspace_uuid).scalar() or 0
    logger.info(f"📋 Product count | count={products_count}")

    # Count data sources
    data_sources_count = db.query(func.count(DataSource.id)).filter(DataSource.workspace_id == workspace_uuid).scalar() or 0
    logger.info(f"📋 Data source count | count={data_sources_count}")

    # Count pipeline runs in current month
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    pipeline_runs_count = (
        db.query(func.count(PipelineRun.id))
        .filter(and_(PipelineRun.workspace_id == workspace_uuid, PipelineRun.started_at >= month_start))
        .scalar()
        or 0
    )
    logger.info(f"📋 Pipeline runs this month | count={pipeline_runs_count}")

    # Calculate total raw files size in bytes (sum across all raw files in workspace)
    raw_files_size_bytes = (
        db.query(func.sum(RawFile.file_size))
        .filter(RawFile.workspace_id == workspace_uuid)
        .scalar() or 0
    )
    # Convert to MB (1 MB = 1024 * 1024 bytes)
    raw_files_size_mb = raw_files_size_bytes / (1024 * 1024)
    logger.info(f"💾 Raw files total size | size_mb={raw_files_size_mb}")

    usage = {
        "products": products_count,
        "data_sources": data_sources_count,
        "pipeline_runs_this_month": pipeline_runs_count,
        "raw_files_size_mb": round(raw_files_size_mb, 2),  # Round to 2 decimal places
    }

    logger.info(f"✅ Workspace usage calculated | usage={usage}")
    return usage


def check_billing_limits(workspace_id: str, limit_type: str, current_count: int, db: Session) -> bool:
    """
    Check if workspace is within billing limits.

    Args:
        workspace_id: Workspace ID (string or UUID)
        limit_type: Type of limit to check
        current_count: Current count/value of the resource
        db: Database session

    Returns:
        True if within limits, False otherwise
    """
    logger.info(f"💳 Checking billing limits | workspace_id={workspace_id}, limit_type={limit_type}, current_count={current_count}")

    try:
        from uuid import UUID

        # Convert string to UUID if needed
        workspace_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

        billing_profile = db.query(BillingProfile).filter(BillingProfile.workspace_id == workspace_uuid).first()

        if not billing_profile:
            logger.warning(f"💳 No billing profile found | workspace_id={workspace_id}")
            return True  # No billing profile, assume free tier

        # Get plan limits from central configuration
        plan_name = (
            billing_profile.plan.value.lower() if hasattr(billing_profile.plan, "value") else str(billing_profile.plan).lower()
        )
        limit = get_plan_limit(plan_name, limit_type)

        if limit is None:
            logger.info(f"✅ No limit defined for | limit_type={limit_type}")
            return True  # No limit defined

        if limit == -1:
            logger.info(f"✅ Unlimited | limit_type={limit_type}")
            return True  # Unlimited

        within_limit = current_count < limit
        logger.info(f"{'✅' if within_limit else '❌'} Limit check result | limit={limit}, current={current_count}")
        return within_limit

    except Exception as e:
        logger.warning(f"⚠️ Billing limit check failed | workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        return True  # Default to allowing if check fails


def calculate_workspace_raw_files_size_mb(workspace_id: str, db: Session) -> float:
    """
    Calculate total raw files size in MB for a workspace.

    Args:
        workspace_id: Workspace ID (string or UUID)
        db: Database session

    Returns:
        Total size in MB (rounded to 2 decimal places)
    """
    try:
        workspace_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

        # Sum all raw file sizes for this workspace
        total_bytes = (
            db.query(func.sum(RawFile.file_size))
            .filter(RawFile.workspace_id == workspace_uuid)
            .scalar() or 0
        )

        # Convert to MB
        size_mb = total_bytes / (1024 * 1024)
        return round(size_mb, 2)
    except Exception as e:
        logger.error(f"Error calculating workspace raw files size: {e}", exc_info=True)
        return 0.0
