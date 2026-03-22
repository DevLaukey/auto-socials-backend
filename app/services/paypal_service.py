"""
PayPal Payment Service

Handles:
- Creating payment orders
- Capturing payments
- Webhook verification
- Subscription management
"""

import json
import logging
import requests
import base64
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class PayPalService:
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.api_url = settings.PAYPAL_API_URL
        self.access_token = None
        self.token_expires_at = None

    def _get_auth_header(self) -> str:
        """Get Basic Auth header for token requests."""
        auth_string = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        return f"Basic {encoded}"

    def _get_access_token(self) -> str:
        """Get or refresh PayPal access token."""
        if self.access_token and self.token_expires_at and datetime.utcnow() < self.token_expires_at:
            return self.access_token

        url = f"{self.api_url}/v1/oauth2/token"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()

            self.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 300)

            return self.access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get PayPal access token: {e}")
            raise RuntimeError("PayPal authentication failed")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for PayPal API requests."""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def create_subscription_order(
        self,
        user_id: int,
        plan_name: str,
        amount: float,
        currency: str = "USD",
        return_url: str = None,
        cancel_url: str = None
    ) -> Dict[str, Any]:
        """
        Create a PayPal order for subscription payment.
        """
        url = f"{self.api_url}/v2/checkout/orders"

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": f"sub_{user_id}_{int(datetime.utcnow().timestamp())}",
                "description": f"Subscription: {plan_name}",
                "amount": {
                    "currency_code": currency,
                    "value": f"{amount:.2f}"
                },
                "soft_descriptor": f"{settings.APP_NAME[:22]}"
            }],
            "application_context": {
                "brand_name": settings.APP_NAME,
                "landing_page": "BILLING",
                "user_action": "PAY_NOW",
                "return_url": return_url or f"{settings.FRONTEND_BASE_URL}/payment/success",
                "cancel_url": cancel_url or f"{settings.FRONTEND_BASE_URL}/payment/cancel",
                "shipping_preference": "NO_SHIPPING"
            }
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            order_data = response.json()
            
            # Log order creation
            logger.info(f"Created PayPal order {order_data['id']} for user {user_id}, amount: {amount} {currency}")
            
            return order_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create PayPal order: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to create payment order")

    def create_post_payment_order(
        self,
        user_id: int,
        post_data: Dict,
        amount: float = 1.00,
        currency: str = "USD"
    ) -> Dict[str, Any]:
        """
        Create a PayPal order for pay-per-post payment.
        """
        url = f"{self.api_url}/v2/checkout/orders"

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": f"post_{user_id}_{int(datetime.utcnow().timestamp())}",
                "description": "Social Media Post",
                "amount": {
                    "currency_code": currency,
                    "value": f"{amount:.2f}"
                },
                "soft_descriptor": f"{settings.APP_NAME[:22]}"
            }],
            "application_context": {
                "brand_name": settings.APP_NAME,
                "landing_page": "BILLING",
                "user_action": "PAY_NOW",
                "return_url": f"{settings.FRONTEND_BASE_URL}/posts/payment-success",
                "cancel_url": f"{settings.FRONTEND_BASE_URL}/posts/payment-cancel",
                "shipping_preference": "NO_SHIPPING"
            }
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            order_data = response.json()
            
            logger.info(f"Created PayPal post order {order_data['id']} for user {user_id}")
            
            return order_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create PayPal post payment order: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to create payment order")

    def capture_order(self, order_id: str) -> Dict[str, Any]:
        """
        Capture a PayPal order after approval.
        """
        url = f"{self.api_url}/v2/checkout/orders/{order_id}/capture"

        try:
            response = requests.post(url, headers=self._get_headers())
            response.raise_for_status()
            capture_data = response.json()
            
            logger.info(f"Captured PayPal order {order_id}, status: {capture_data.get('status')}")
            
            return capture_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to capture PayPal order {order_id}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to capture payment")

    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """
        Get details of a PayPal order.
        """
        url = f"{self.api_url}/v2/checkout/orders/{order_id}"

        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get PayPal order {order_id}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to get order details")

    def refund_payment(self, capture_id: str, amount: float = None, currency: str = "USD") -> Dict[str, Any]:
        """
        Refund a captured payment.
        
        Args:
            capture_id: The capture ID from the payment
            amount: Amount to refund (None for full refund)
            currency: Currency code
        """
        url = f"{self.api_url}/v2/payments/captures/{capture_id}/refund"
        
        payload = {}
        if amount is not None:
            payload["amount"] = {
                "value": f"{amount:.2f}",
                "currency_code": currency
            }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            refund_data = response.json()
            
            logger.info(f"Refunded payment {capture_id}, amount: {amount if amount else 'full'}")
            
            return refund_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refund payment {capture_id}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response body: {e.response.text}")
            raise RuntimeError("Failed to refund payment")

    def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        body: str
    ) -> bool:
        """
        Verify PayPal webhook signature.
        """
        if not settings.PAYPAL_WEBHOOK_ID:
            logger.warning("PayPal webhook ID not configured")
            return True  # Skip verification in development

        url = f"{self.api_url}/v1/notifications/verify-webhook-signature"

        payload = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": json.loads(body)
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            result = response.json()
            is_valid = result.get("verification_status") == "SUCCESS"
            
            if is_valid:
                logger.info("PayPal webhook signature verified")
            else:
                logger.warning(f"PayPal webhook signature verification failed: {result}")
            
            return is_valid

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to verify webhook signature: {e}")
            return False

    def store_webhook_event(self, event_data: Dict) -> bool:
        """
        Store a webhook event in the database for later processing.
        """
        from app.services.database import get_conn
        
        event_id = event_data.get("id")
        event_type = event_data.get("event_type")
        resource = event_data.get("resource", {})
        resource_type = resource.get("resource_type")
        resource_id = resource.get("id")
        summary = event_data.get("summary", "")
        
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO auth.paypal_webhook_events 
                        (event_id, event_type, resource_type, resource_id, resource, summary, processed)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                        ON CONFLICT (event_id) DO NOTHING
                        RETURNING id
                    """, (event_id, event_type, resource_type, resource_id, json.dumps(resource), summary))
                    
                    result = cur.fetchone()
                    conn.commit()
                    
                    if result:
                        logger.info(f"Stored PayPal webhook event {event_id} of type {event_type}")
                    else:
                        logger.info(f"PayPal webhook event {event_id} already processed")
                    
                    return result is not None
                    
        except Exception as e:
            logger.error(f"Failed to store webhook event: {e}")
            return False