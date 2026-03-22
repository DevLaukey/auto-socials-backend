"""
DM automation service for Instagram, Twitter, and YouTube.

Handles:
- Sending DMs
- Managing conversation threads
- AI-powered replies
"""

import logging
import time
import random
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json

from app.services.instagram_service import InstagramService
from app.services.twitter_service import TwitterService
from app.services.ai_comment_service import AICommentService
from app.services.database import get_conn
from app.services.auth_database import get_twitter_token

logger = logging.getLogger(__name__)


class DMService:
    def __init__(self, account_id: int, platform: str):
        """
        Initialize DM service for a specific account and platform.
        
        Args:
            account_id: Database account ID
            platform: 'instagram', 'twitter', etc.
        """
        self.account_id = account_id
        self.platform = platform.lower()
        self.ai_service = AICommentService(self.platform)
        self.client = None
        
        # Initialize platform-specific client
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the platform-specific client."""
        try:
            if self.platform == "instagram":
                self.client = InstagramService(self.account_id)
                self.client.login()
                logger.info(f"Instagram DM service initialized for account {self.account_id}")

            elif self.platform == "twitter":
                creds = get_twitter_token(self.account_id)
                if not creds:
                    raise ValueError(f"No Twitter credentials found for account {self.account_id}")
                self.client = TwitterService(self.account_id, creds)
                logger.info(f"Twitter DM service initialized for account {self.account_id}")

            elif self.platform == "youtube":
                # YouTube has no public API for sending DMs to arbitrary users.
                # Promotional messaging on YouTube should use Community Posts instead.
                logger.warning(
                    "YouTube does not support direct messages via API. "
                    "Use Community Posts for channel-wide promotions."
                )

            else:
                logger.warning(f"Unsupported platform for DM service: {self.platform}")
                
        except Exception as e:
            logger.error(f"Failed to initialize {self.platform} client for account {self.account_id}: {e}")
            raise

    def send_dm(
        self,
        recipient: str,
        message: str,
        campaign_id: Optional[int] = None,
        dm_job_id: Optional[int] = None
    ) -> bool:
        """
        Send a direct message.
        
        Args:
            recipient: Username or ID of recipient
            message: Message text to send
            campaign_id: Optional campaign ID for tracking
            dm_job_id: Optional job ID for status updates
            
        Returns:
            bool: True if successful
        """
        if not self.client:
            logger.error(f"No client initialized for {self.platform}")
            return False

        try:
            if self.platform == "instagram":
                self.client.send_dm(recipient, message)

            elif self.platform == "twitter":
                # Twitter DMs require recipient ID, not username
                user = self.client.client.get_user(username=recipient)
                if not user or not user.data:
                    raise ValueError(f"Could not find Twitter user: {recipient}")
                self.client.client.create_direct_message(
                    participant_id=user.data.id,
                    text=message
                )

            elif self.platform == "youtube":
                logger.warning(
                    f"Skipping DM to {recipient}: YouTube does not support direct messages via API."
                )
                return False

            # Log success and update job status
            if dm_job_id:
                self._update_job_status(dm_job_id, "sent")
                self._log_conversation(recipient, message, is_from_me=True)
            
            logger.info(f"[DM][{self.platform}] Sent to {recipient}: {message[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"[DM][{self.platform}] Failed to send to {recipient}: {e}")
            if dm_job_id:
                self._update_job_status(dm_job_id, "failed", error=str(e))
            return False

    def send_ai_dm(
        self,
        recipient: str,
        context: Optional[Dict] = None,
        campaign_id: Optional[int] = None
    ) -> bool:
        """
        Send an AI-generated DM with conversation continuity.
        
        Args:
            recipient: Username/ID of recipient
            context: Additional context for AI
            campaign_id: Campaign ID for tracking
            
        Returns:
            bool: True if successful
        """
        try:
            # Get conversation history
            conversation = self._get_conversation(recipient)
            
            # Generate AI reply
            message = self.ai_service.generate_dm_reply(
                conversation_history=conversation.get('history', []),
                recipient_info={
                    'username': recipient,
                    'context': context or {}
                },
                tone=context.get('tone', 'friendly') if context else 'friendly'
            )
            
            if not message:
                logger.warning(f"AI generated empty message for {recipient}, using fallback")
                message = self._get_fallback_message(context)
            
            # Send the message
            success = self.send_dm(recipient, message, campaign_id)
            
            if success and context:
                # Update conversation context
                self._update_conversation_context(recipient, context)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send AI DM to {recipient}: {e}")
            return False

    def _get_conversation(self, recipient: str) -> Dict[str, Any]:
        """Get conversation history and context for a recipient."""
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get conversation
                cur.execute("""
                    SELECT id, context, last_message_at
                    FROM dm_conversations
                    WHERE account_id = %s AND recipient_username = %s
                """, (self.account_id, recipient))
                conv = cur.fetchone()
                
                if not conv:
                    return {'history': [], 'context': {}, 'conversation_id': None}
                
                # Get last 10 messages
                cur.execute("""
                    SELECT content, is_from_me, ai_generated, created_at
                    FROM dm_messages
                    WHERE conversation_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                """, (conv['id'],))
                
                messages = cur.fetchall()
                
                return {
                    'history': [
                        {
                            'content': m['content'],
                            'is_from_me': m['is_from_me'],
                            'ai_generated': m['ai_generated'],
                            'created_at': m['created_at'].isoformat() if m['created_at'] else None
                        }
                        for m in reversed(messages)  # Chronological order
                    ],
                    'context': conv['context'] or {},
                    'conversation_id': conv['id']
                }

    def _log_conversation(self, recipient: str, message: str, is_from_me: bool):
        """Log a message in the conversation history."""
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Get or create conversation
                cur.execute("""
                    INSERT INTO dm_conversations (account_id, recipient_username, last_message_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (account_id, recipient_username) DO UPDATE SET
                        last_message_at = NOW()
                    RETURNING id
                """, (self.account_id, recipient))
                
                result = cur.fetchone()
                conv_id = result['id'] if result else None
                
                if conv_id:
                    # Log message
                    cur.execute("""
                        INSERT INTO dm_messages (conversation_id, content, is_from_me, ai_generated)
                        VALUES (%s, %s, %s, %s)
                    """, (conv_id, message, is_from_me, True))
                    
                conn.commit()

    def _update_conversation_context(self, recipient: str, context: Optional[Dict]):
        """Update conversation context with new information."""
        if not context:
            return
            
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Merge new context with existing
                cur.execute("""
                    UPDATE dm_conversations
                    SET context = context || %s
                    WHERE account_id = %s AND recipient_username = %s
                """, (json.dumps(context), self.account_id, recipient))
                conn.commit()

    def _update_job_status(self, job_id: int, status: str, error: Optional[str] = None):
        """Update DM job status in database."""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE dm_jobs
                    SET status = %s,
                        error_message = %s,
                        executed_time = CASE WHEN %s = 'completed' THEN NOW() ELSE NULL END
                    WHERE id = %s
                """, (status, error, status, job_id))
                conn.commit()

    def _get_fallback_message(self, context: Optional[Dict] = None) -> str:
        """Get a fallback message if AI generation fails."""
        tone = context.get('tone', 'friendly') if context else 'friendly'
        
        fallbacks = {
            "friendly": "Thanks for reaching out! How can I help you today?",
            "professional": "Thank you for your message. I'll get back to you shortly.",
            "casual": "Hey! Thanks for the message. What's up?",
            "enthusiastic": "Thanks so much for reaching out! Really excited to connect!",
            "helpful": "Hi there! I'd be happy to help. What can I do for you?"
        }
        return fallbacks.get(tone, fallbacks["friendly"])