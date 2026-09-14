"""Support ticket submission."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from core.models import TicketReceipt, TicketRequest
from dependencies import CurrentUser, require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=TicketReceipt)
async def submit_ticket(req: TicketRequest, _user: CurrentUser = Depends(require_user)) -> TicketReceipt:
    """Route a ticket to the configured sink.

    Phase 2 wires `stub` (logs only) and `email` (logs only — real SMTP
    integration is Phase 3 deliverable). The `servicenow` sink is reserved
    for the production deployment.
    """
    ticket_id = uuid.uuid4().hex[:12]

    if settings.support_sink == "email":
        logger.info(
            "TICKET %s would email to %s subject=%r body_len=%d",
            ticket_id, settings.support_email_to, req.subject, len(req.body),
        )
        return TicketReceipt(ok=True, ticket_id=ticket_id, sink="email")

    if settings.support_sink == "servicenow":
        # Not yet implemented — fail loudly so it can't silently drop tickets.
        raise HTTPException(status_code=501,
                            detail="ServiceNow sink not yet implemented.")

    # Default: stub
    logger.info(
        "TICKET %s [stub] from=%r subject=%r",
        ticket_id, req.email, req.subject,
    )
    return TicketReceipt(ok=True, ticket_id=ticket_id, sink="stub")
