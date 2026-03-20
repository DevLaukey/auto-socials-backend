"""
Twitter token refresh service.
Runs periodically to keep tokens valid.
"""

import logging
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional
import requests

from app.services.auth_database import (
    get_conn, 
    update_twitter_token, 
    get_all_twitter_accounts_with_tokens,
    delete_twitter_token
)
from app.config import settings

logger = logging.getLogger(__name__)


def refresh_twitter_token(account_id: int, refresh_token: str) -> bool:
    """
    Refresh an expired Twitter token.
    
    Args:
        account_id: The account ID to refresh
        refresh_token: The refresh token to use
    
    Returns:
        bool: True if refresh successful, False otherwise
    """
    token_url = "https://api.twitter.com/2/oauth2/token"
    
    if not settings.TWITTER_CLIENT_ID or not settings.TWITTER_CLIENT_SECRET:
        logger.error("Twitter client credentials not configured")
        return False
    
    auth = requests.auth.HTTPBasicAuth(
        settings.TWITTER_CLIENT_ID,
        settings.TWITTER_CLIENT_SECRET
    )
    
    data = {
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
        'client_id': settings.TWITTER_CLIENT_ID
    }
    
    try:
        logger.info(f"Attempting to refresh token for account {account_id}")
        response = requests.post(token_url, auth=auth, data=data)
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed with status {response.status_code}: {response.text}")
            
            # If refresh token is invalid, delete it
            if response.status_code in [400, 401, 403]:
                logger.warning(f"Refresh token invalid for account {account_id}, deleting")
                delete_twitter_token(account_id)
            return False
        
        tokens = response.json()
        
        # Calculate new expiry
        expires_in = tokens.get('expires_in', 7200)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        # Update the token in database
        success = update_twitter_token(
            account_id=account_id,
            access_token=tokens['access_token'],
            expires_at=expires_at,
            refresh_token=tokens.get('refresh_token')  # Some providers return new refresh token
        )
        
        if success:
            logger.info(f"Successfully refreshed Twitter token for account {account_id}")
        else:
            logger.error(f"Failed to update token in database for account {account_id}")
        
        return success
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error refreshing token for account {account_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error refreshing token for account {account_id}: {e}")
        return False


def refresh_all_twitter_tokens():
    """Refresh all expired or soon-to-expire Twitter tokens."""
    logger.info("Starting scheduled refresh of all Twitter tokens")
    
    try:
        accounts = get_all_twitter_accounts_with_tokens()
        
        if not accounts:
            logger.debug("No Twitter accounts found with tokens")
            return
        
        logger.info(f"Found {len(accounts)} Twitter accounts to check")
        
        for account in accounts:
            account_id = account['account_id']
            refresh_token = account.get('refresh_token')
            expires_at = account.get('expires_at')
            
            if not refresh_token:
                logger.warning(f"Account {account_id} has no refresh token, skipping")
                continue
            
            # Check if token is expired or will expire soon
            now = datetime.now(timezone.utc)
            needs_refresh = False
            
            if expires_at:
                # Convert to timezone-aware if naive
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                
                # Refresh if expired or will expire in next hour
                if expires_at <= now + timedelta(hours=1):
                    needs_refresh = True
            else:
                # No expiry date, assume it needs refresh
                needs_refresh = True
            
            if needs_refresh:
                logger.info(f"Token for account {account_id} needs refresh (expires at {expires_at})")
                refresh_twitter_token(account_id, refresh_token)
            else:
                logger.debug(f"Token for account {account_id} is still valid until {expires_at}")
                
    except Exception as e:
        logger.error(f"Error in refresh_all_twitter_tokens: {e}")


def start_token_refresh_scheduler(interval_minutes: int = 30):
    """
    Start a background thread that periodically refreshes tokens.
    
    Args:
        interval_minutes: How often to run the refresh check (default: 30 minutes)
    """
    def scheduler_loop():
        logger.info(f"Twitter token refresh scheduler started (interval: {interval_minutes} minutes)")
        
        while True:
            try:
                refresh_all_twitter_tokens()
            except Exception as e:
                logger.error(f"Error in token refresh scheduler: {e}")
            
            # Sleep for the specified interval
            time.sleep(interval_minutes * 60)
    
    # Start the scheduler in a daemon thread
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    logger.info(f"Twitter token refresh scheduler thread started")


# For manual one-time refresh
def refresh_single_twitter_token(account_id: int) -> bool:
    """
    Manually refresh a single Twitter token.
    
    Args:
        account_id: The account ID to refresh
    
    Returns:
        bool: True if refresh successful, False otherwise
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT refresh_token
                FROM twitter_tokens
                WHERE account_id = %s
            """, (account_id,))
            result = cur.fetchone()
    
    if not result or not result['refresh_token']:
        logger.error(f"No refresh token found for account {account_id}")
        return False
    
    return refresh_twitter_token(account_id, result['refresh_token'])