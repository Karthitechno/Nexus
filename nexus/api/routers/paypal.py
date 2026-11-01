"""PayPal status endpoint."""
from fastapi import APIRouter
from nexus.api.deps import get_executor
import os

router = APIRouter()

@router.get("/paypal/status")
def paypal_status():
    executor = get_executor()
    configured = executor.oauth.is_configured()
    base_url = os.environ.get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    return {
        "configured": configured,
        "base_url": base_url if configured else None,
        "message": "PayPal credentials detected." if configured else "PayPal credentials not configured. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env",
    }
