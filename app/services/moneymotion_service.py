"""
MoneyMotion Payment Service

Handles:
- Creating payment orders
- Capturing payments
- Webhook verification
"""

import json
import logging
import requests
import hmac
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class MoneyMotionService:
    def __init__(self):
        # Only API key is required for API calls
        self.api_key = settings.MONEYMOTION_API_KEY
        self.webhook_secret = settings.MONEYMOTION_WEBHOOK_SECRET  # Optional
        self.api_url = settings.MONEYMOTION_API_URL

    def _get_headers(self, currency: str = "USD") -> Dict[str, str]:
        """Get headers for MoneyMotion API requests."""
        key = settings.MONEYMOTION_API_KEY
        return {
            "X-API-Key": key,
            "x-currency": currency,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def create_payment(
        self,
        user_id: int,
        amount: float,
        currency: str = "USD",
        description: str = "Payment",
        reference: str = None,
        return_url: str = None,
        cancel_url: str = None,
        webhook_url: str = None,
        email: str = None
    ) -> Dict[str, Any]:
        """
        Create a payment order with MoneyMotion.

        Args:
            user_id: User ID for reference
            amount: Payment amount
            currency: Currency code (default: KES)
            description: Payment description
            reference: Unique reference ID
            return_url: URL to redirect after successful payment
            cancel_url: URL to redirect after cancelled payment
            webhook_url: Webhook URL for payment notifications
            email: User email for MoneyMotion userInfo

        Returns:
            Payment data with checkoutSessionId and checkoutUrl
        """
        if not settings.MONEYMOTION_API_KEY:
            raise RuntimeError("MoneyMotion API key not configured")

        url = f"{self.api_url}/checkoutSessions.createCheckoutSession"

        # Generate reference if not provided
        if not reference:
            reference = f"payment_{user_id}_{int(datetime.utcnow().timestamp())}"

        success_url = return_url or f"{settings.FRONTEND_BASE_URL}/payment/success"
        cancel_url = cancel_url or f"{settings.FRONTEND_BASE_URL}/payment/cancel"

        inner = {
            "description": description,
            "urls": {
                "success": success_url,
                "cancel": cancel_url,
                "failure": cancel_url,
            },
            "userInfo": {"email": email or ""},
            "lineItems": [
                {
                    "name": description,
                    "description": description,
                    "pricePerItemInCents": int(amount * 100),
                    "quantity": 1,
                }
            ],
            "metadata": {"reference": reference, "user_id": str(user_id)},
        }

        payload = {"json": inner}

        try:
            response = requests.post(url, headers=self._get_headers(currency), json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            # tRPC response shape: { result: { data: { json: { checkoutSessionId, checkoutUrl } } } }
            session = data.get("result", {}).get("data", {}).get("json", {})

            logger.info(f"Created MoneyMotion payment {session.get('checkoutSessionId')} for user {user_id}, amount: {amount} {currency}")

            return session

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create MoneyMotion payment: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to create payment order")
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Get status of a payment."""
        if not settings.MONEYMOTION_API_KEY:
            raise RuntimeError("MoneyMotion API key not configured")

        url = f"{self.api_url}/checkoutSessions.getCompletedOrPendingCheckoutSessionInfo"
        
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get payment status {payment_id}: {e}")
            raise RuntimeError("Failed to get payment status")
    
    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify MoneyMotion webhook signature."""
        if not self.webhook_secret:
            logger.warning("MoneyMotion webhook secret not configured - skipping verification")
            return True  # Skip verification if no secret configured
        
        try:
            # MoneyMotion uses HMAC-SHA256 for webhook verification
            expected = hmac.new(
                self.webhook_secret.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()
            
            # Use constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(expected.lower(), signature.lower())
            
            if is_valid:
                logger.info("MoneyMotion webhook signature verified")
            else:
                logger.warning(f"MoneyMotion webhook signature verification failed. Expected: {expected}, Got: {signature}")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Failed to verify webhook signature: {e}")
            return False