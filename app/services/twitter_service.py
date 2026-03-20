"""
Twitter/X posting service.

Handles:
- OAuth 2.0 authentication
- Tweet posting (text, images, videos)
- Thread creation
- Rate limiting
"""

import tweepy
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TwitterService:
    def __init__(self, account_id: int, credentials: dict):
        """
        Initialize Twitter client with OAuth 2.0 credentials.
        
        Args:
            account_id: Database account ID
            credentials: {
                'access_token': str,
                'refresh_token': str,
                'expires_at': datetime,
                'client_id': str,
                'client_secret': str
            }
        """
        self.account_id = account_id
        
        # Get client credentials from settings if not provided in credentials
        from app.config import settings
        client_id = credentials.get('client_id', settings.TWITTER_CLIENT_ID)
        client_secret = credentials.get('client_secret', settings.TWITTER_CLIENT_SECRET)
        
        self.client = tweepy.Client(
            bearer_token=None,  # Not needed for user context
            access_token=credentials['access_token'],
            refresh_token=credentials.get('refresh_token'),
            wait_on_rate_limit=True,
            consumer_key=client_id,
            consumer_secret=client_secret
        )
        
        # For media upload (v1.1 API required)
        # Note: Twitter API v2 doesn't support media upload directly
        # This uses OAuth 1.0a for media upload
        self.v1_api = tweepy.API(
            tweepy.OAuth1UserHandler(
                consumer_key=client_id,
                consumer_secret=client_secret,
                access_token=credentials['access_token'],
                access_token_secret=credentials.get('access_token_secret')
            )
        )

    def post_tweet(
        self,
        text: str,
        media_paths: Optional[List[str]] = None,
        reply_to_tweet_id: Optional[str] = None,
        quote_tweet_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Post a tweet with optional media.
        
        Returns: {
            'tweet_id': str,
            'text': str,
            'media_ids': List[str]
        }
        """
        media_ids = []
        
        # Upload media if any
        if media_paths:
            for path in media_paths:
                try:
                    media = self.v1_api.media_upload(path)
                    media_ids.append(media.media_id_string)
                    logger.info(f"Media uploaded successfully: {media.media_id_string}")
                except Exception as e:
                    logger.error(f"Media upload failed for {path}: {e}")
                    raise

        # Prepare parameters
        params = {
            'text': text[:280],  # Twitter character limit
        }
        
        if media_ids:
            params['media_ids'] = media_ids
            
        if reply_to_tweet_id:
            params['in_reply_to_tweet_id'] = reply_to_tweet_id
            
        if quote_tweet_id:
            params['quote_tweet_id'] = quote_tweet_id

        # Post tweet
        try:
            response = self.client.create_tweet(**params)
            
            if not response.data or 'id' not in response.data:
                raise RuntimeError("No tweet ID returned from Twitter API")
            
            tweet_id = response.data['id']
            logger.info(f"Tweet posted successfully: {tweet_id}")
            
            return {
                'tweet_id': tweet_id,
                'text': text,
                'media_ids': media_ids
            }
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            raise

    def post_thread(self, tweets: List[str]) -> List[str]:
        """
        Post a thread of tweets.
        
        Args:
            tweets: List of tweet texts
            
        Returns:
            List of tweet IDs in order
        """
        tweet_ids = []
        previous_tweet_id = None
        
        for i, text in enumerate(tweets):
            try:
                params = {'text': text[:280]}
                
                if previous_tweet_id:
                    params['in_reply_to_tweet_id'] = previous_tweet_id
                    
                response = self.client.create_tweet(**params)
                
                if not response.data or 'id' not in response.data:
                    raise RuntimeError(f"No tweet ID returned for tweet {i+1}")
                
                tweet_id = response.data['id']
                tweet_ids.append(tweet_id)
                previous_tweet_id = tweet_id
                
                logger.info(f"Thread tweet {i+1}/{len(tweets)} posted: {tweet_id}")
                
            except Exception as e:
                logger.error(f"Failed to post thread tweet {i+1}: {e}")
                # Return IDs of successfully posted tweets so far
                return tweet_ids
            
        return tweet_ids

    def get_tweet_metrics(self, tweet_id: str) -> Dict[str, int]:
        """Get engagement metrics for a tweet."""
        try:
            response = self.client.get_tweet(
                id=tweet_id,
                expansions=['attachments.media_keys'],
                tweet_fields=['public_metrics', 'created_at']
            )
            
            if not response.data:
                logger.warning(f"No data returned for tweet {tweet_id}")
                return {}
                
            metrics = response.data.public_metrics
            return {
                'likes': metrics.get('like_count', 0),
                'retweets': metrics.get('retweet_count', 0),
                'replies': metrics.get('reply_count', 0),
                'quotes': metrics.get('quote_count', 0),
                'impressions': metrics.get('impression_count', 0),
                'bookmarks': metrics.get('bookmark_count', 0)
            }
        except Exception as e:
            logger.error(f"Failed to get metrics for tweet {tweet_id}: {e}")
            return {}