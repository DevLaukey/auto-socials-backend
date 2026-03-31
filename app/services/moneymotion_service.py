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

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for MoneyMotion API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def create_payment(
        self,
        user_id: int,
        amount: float,
        currency: str = "KES",
        description: str = "Payment",
        reference: str = None,
        return_url: str = None,
        cancel_url: str = None,
        webhook_url: str = None
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
        
        Returns:
            Payment data with checkout URL
        """
        if not self.api_key:
            raise RuntimeError("MoneyMotion API key not configured")
        
        url = f"{self.api_url}/payments"
        
        # Generate reference if not provided
        if not reference:
            reference = f"payment_{user_id}_{int(datetime.utcnow().timestamp())}"
        
        payload = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "reference": reference,
            "return_url": return_url or f"{settings.FRONTEND_BASE_URL}/payment/success",
            "cancel_url": cancel_url or f"{settings.FRONTEND_BASE_URL}/payment/cancel",
            "webhook_url": webhook_url or f"{settings.API_BASE_URL}/api/moneymotion/webhook"
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            payment_data = response.json()
            
            logger.info(f"Created MoneyMotion payment {payment_data.get('id')} for user {user_id}, amount: {amount} {currency}")
            
            return payment_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create MoneyMotion payment: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to create payment order")
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Get status of a payment."""
        if not self.api_key:
            raise RuntimeError("MoneyMotion API key not configured")
        
        url = f"{self.api_url}/payments/{payment_id}"
        
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