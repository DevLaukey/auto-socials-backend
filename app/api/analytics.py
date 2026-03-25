from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta

from app.api.deps import get_current_user
from app.services.database import (
    get_post_overview,
    get_platform_breakdown,
    get_daily_post_counts,
    get_engagement_stats,
    calculate_account_health,
    get_conn,
)
from app.services.auth_database import get_conn as get_auth_conn

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def get_analytics(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    current_user=Depends(get_current_user)
):
    """
    Get comprehensive analytics dashboard data including:
    - Post performance metrics
    - Platform breakdown
    - Engagement automation stats (comments, DMs)
    - Account health indicators
    - Twitter/X specific metrics
    """
    user_id = current_user["id"]
    
    # Get existing analytics
    overview = get_post_overview(user_id)
    platform = get_platform_breakdown(user_id)
    activity = get_daily_post_counts(user_id, days)
    engagement = get_engagement_stats(user_id)
    health = calculate_account_health(user_id)
    
    # Get new engagement automation stats
    automation_stats = get_automation_stats(user_id, days)
    
    # Get Twitter-specific metrics
    twitter_metrics = get_twitter_metrics(user_id, days)
    
    # Get conversation analytics
    conversation_stats = get_conversation_stats(user_id, days)
    
    # Get daily engagement trends
    engagement_trends = get_engagement_trends(user_id, days)
    
    return {
        "overview": overview,
        "platform_breakdown": platform,
        "posting_activity": activity,
        "engagement": engagement,
        "account_health": health,
        "automation": automation_stats,
        "twitter": twitter_metrics,
        "conversations": conversation_stats,
        "trends": engagement_trends,
        "period": {
            "days": days,
            "start_date": (datetime.utcnow() - timedelta(days=days)).isoformat(),
            "end_date": datetime.utcnow().isoformat()
        }
    }


@router.get("/engagement/automation")
def get_automation_analytics(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    current_user=Depends(get_current_user)
):
    """
    Get detailed analytics for comment and DM automation.
    """
    return get_automation_stats(current_user["id"], days)


@router.get("/engagement/comments")
def get_comment_analytics(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    status: Optional[str] = Query(None, description="Filter by status (completed, pending, failed)"),
    current_user=Depends(get_current_user)
):
    """
    Get detailed analytics for comment jobs.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Base query
            status_filter = "AND status = %s" if status else ""
            params = [current_user["id"]]
            if status:
                params.append(status)
            
            # Get comment jobs stats
            cur.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status = 'processing') as processing,
                    AVG(EXTRACT(EPOCH FROM (executed_time - created_at))) as avg_delay_seconds,
                    MAX(executed_time) as last_executed,
                    MIN(created_at) as first_job
                FROM comment_jobs
                WHERE user_id = %s
                AND created_at > NOW() - INTERVAL '%s days'
                {status_filter}
            """, tuple(params + [days]))
            
            summary = cur.fetchone()
            
            # Get platform breakdown
            cur.execute("""
                SELECT 
                    a.platform,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE cj.status = 'completed') as completed,
                    AVG(EXTRACT(EPOCH FROM (cj.executed_time - cj.created_at))) as avg_delay
                FROM comment_jobs cj
                JOIN accounts a ON a.id = cj.account_id
                WHERE cj.user_id = %s
                AND cj.created_at > NOW() - INTERVAL '%s days'
                GROUP BY a.platform
                ORDER BY total DESC
            """, (current_user["id"], days))
            
            platform_breakdown = cur.fetchall()
            
            # Get daily comment activity
            cur.execute("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as successful
                FROM comment_jobs
                WHERE user_id = %s
                AND created_at > NOW() - INTERVAL '%s days'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """, (current_user["id"], days))
            
            daily_activity = cur.fetchall()
    
    return {
        "summary": {
            "total": summary['total'] if summary else 0,
            "completed": summary['completed'] if summary else 0,
            "pending": summary['pending'] if summary else 0,
            "failed": summary['failed'] if summary else 0,
            "processing": summary['processing'] if summary else 0,
            "success_rate": round(
                (summary['completed'] / summary['total'] * 100) 
                if summary and summary['total'] > 0 else 0, 2
            ),
            "avg_delay_minutes": round(
                (summary['avg_delay_seconds'] / 60) 
                if summary and summary['avg_delay_seconds'] else 0, 1
            ),
            "last_executed": summary['last_executed'] if summary else None,
            "first_job": summary['first_job'] if summary else None
        },
        "platform_breakdown": [
            {
                "platform": row["platform"],
                "total": row["total"],
                "completed": row["completed"],
                "success_rate": round((row["completed"] / row["total"] * 100) if row["total"] > 0 else 0, 2),
                "avg_delay_minutes": round((row["avg_delay"] / 60) if row["avg_delay"] else 0, 1)
            }
            for row in platform_breakdown
        ],
        "daily_activity": [
            {
                "date": row["date"].isoformat() if row["date"] else None,
                "total": row["total"],
                "successful": row["successful"]
            }
            for row in daily_activity
        ]
    }


@router.get("/engagement/dms")
def get_dm_analytics(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    status: Optional[str] = Query(None, description="Filter by status (completed, pending, failed)"),
    current_user=Depends(get_current_user)
):
    """
    Get detailed analytics for DM jobs and conversations.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Base query for DM jobs
            status_filter = "AND status = %s" if status else ""
            params = [current_user["id"]]
            if status:
                params.append(status)
            
            cur.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status = 'processing') as processing,
                    AVG(EXTRACT(EPOCH FROM (executed_time - created_at))) as avg_delay_seconds,
                    MAX(executed_time) as last_executed
                FROM dm_jobs
                WHERE user_id = %s
                AND created_at > NOW() - INTERVAL '%s days'
                {status_filter}
            """, tuple(params + [days]))
            
            jobs_summary = cur.fetchone()
            
            # Get conversation stats
            cur.execute("""
                SELECT 
                    COUNT(DISTINCT dc.id) as total_conversations,
                    COUNT(DISTINCT dc.id) FILTER (
                        WHERE dc.last_message_at > NOW() - INTERVAL '7 days'
                    ) as active_conversations,
                    AVG(
                        SELECT COUNT(*) 
                        FROM dm_messages dm 
                        WHERE dm.conversation_id = dc.id
                    ) as avg_messages_per_conversation,
                    MAX(dc.last_message_at) as last_conversation
                FROM dm_conversations dc
                JOIN accounts a ON a.id = dc.account_id
                WHERE a.user_id = %s
            """, (current_user["id"],))
            
            conversation_stats = cur.fetchone()
            
            # Get response time stats
            cur.execute("""
                SELECT 
                    AVG(
                        EXTRACT(EPOCH FROM (
                            SELECT MIN(m2.created_at) - m1.created_at
                            FROM dm_messages m2
                            WHERE m2.conversation_id = m1.conversation_id
                            AND m2.created_at > m1.created_at
                            AND m2.is_from_me = TRUE
                            AND m1.is_from_me = FALSE
                            LIMIT 1
                        ))
                    ) as avg_response_time_seconds
                FROM dm_messages m1
                JOIN dm_conversations dc ON dc.id = m1.conversation_id
                JOIN accounts a ON a.id = dc.account_id
                WHERE a.user_id = %s
                AND m1.is_from_me = FALSE
                AND m1.created_at > NOW() - INTERVAL '%s days'
            """, (current_user["id"], days))
            
            response_time = cur.fetchone()
    
    return {
        "jobs": {
            "total": jobs_summary['total'] if jobs_summary else 0,
            "completed": jobs_summary['completed'] if jobs_summary else 0,
            "pending": jobs_summary['pending'] if jobs_summary else 0,
            "failed": jobs_summary['failed'] if jobs_summary else 0,
            "processing": jobs_summary['processing'] if jobs_summary else 0,
            "success_rate": round(
                (jobs_summary['completed'] / jobs_summary['total'] * 100) 
                if jobs_summary and jobs_summary['total'] > 0 else 0, 2
            ),
            "avg_delay_minutes": round(
                (jobs_summary['avg_delay_seconds'] / 60) 
                if jobs_summary and jobs_summary['avg_delay_seconds'] else 0, 1
            ),
            "last_executed": jobs_summary['last_executed'] if jobs_summary else None
        },
        "conversations": {
            "total": conversation_stats['total_conversations'] if conversation_stats else 0,
            "active_7d": conversation_stats['active_conversations'] if conversation_stats else 0,
            "avg_messages": round(
                conversation_stats['avg_messages_per_conversation'] 
                if conversation_stats and conversation_stats['avg_messages_per_conversation'] else 0, 1
            ),
            "last_activity": conversation_stats['last_conversation'] if conversation_stats else None,
            "avg_response_time_minutes": round(
                (response_time['avg_response_time_seconds'] / 60) 
                if response_time and response_time['avg_response_time_seconds'] else 0, 1
            ) if response_time else 0
        }
    }


@router.get("/twitter/metrics")
def get_twitter_analytics(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    current_user=Depends(get_current_user)
):
    """
    Get Twitter/X specific analytics including tweet performance.
    """
    return get_twitter_metrics(current_user["id"], days)


@router.get("/conversations")
def get_conversation_analytics(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    current_user=Depends(get_current_user)
):
    """
    Get detailed conversation analytics.
    """
    return get_conversation_stats(current_user["id"], days)


@router.get("/trends")
def get_engagement_trends_endpoint(
    days: Optional[int] = Query(30, description="Number of days to analyze"),
    current_user=Depends(get_current_user)
):
    """
    Get engagement trends over time.
    """
    return get_engagement_trends(current_user["id"], days)


# ======================
# Helper Functions
# ======================

def get_automation_stats(user_id: int, days: int = 30) -> dict:
    """Get combined stats for comments and DMs automation."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Comment stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_comments,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_comments,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_comments,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_comments,
                    COALESCE(SUM(attempts), 0) as total_attempts
                FROM comment_jobs
                WHERE user_id = %s
                AND created_at > NOW() - INTERVAL '%s days'
            """, (user_id, days))
            comment_stats = cur.fetchone()
            
            # DM stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_dms,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_dms,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_dms,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_dms,
                    COALESCE(SUM(attempts), 0) as total_attempts
                FROM dm_jobs
                WHERE user_id = %s
                AND created_at > NOW() - INTERVAL '%s days'
            """, (user_id, days))
            dm_stats = cur.fetchone()
            
            # AI usage stats — only dm_messages has ai_generated column
            cur.execute("""
                SELECT COUNT(*) as ai_generated_dms
                FROM dm_messages dm
                JOIN dm_conversations dc ON dm.conversation_id = dc.id
                JOIN accounts a ON a.id = dc.account_id
                WHERE a.user_id = %s AND dm.ai_generated = TRUE
            """, (user_id,))
            ai_stats = cur.fetchone()
    
    total_comments = comment_stats['total_comments'] or 0
    total_dms = dm_stats['total_dms'] or 0
    
    return {
        "comments": {
            "total": total_comments,
            "completed": comment_stats['completed_comments'] or 0,
            "pending": comment_stats['pending_comments'] or 0,
            "failed": comment_stats['failed_comments'] or 0,
            "total_attempts": comment_stats['total_attempts'] or 0,
            "success_rate": round(
                (comment_stats['completed_comments'] / total_comments * 100) 
                if total_comments > 0 else 0, 2
            )
        },
        "dms": {
            "total": total_dms,
            "completed": dm_stats['completed_dms'] or 0,
            "pending": dm_stats['pending_dms'] or 0,
            "failed": dm_stats['failed_dms'] or 0,
            "total_attempts": dm_stats['total_attempts'] or 0,
            "success_rate": round(
                (dm_stats['completed_dms'] / total_dms * 100) 
                if total_dms > 0 else 0, 2
            )
        },
        "ai_usage": {
            "ai_generated_comments": 0,
            "ai_generated_dms": ai_stats['ai_generated_dms'] or 0,
            "total_ai_generated": ai_stats['ai_generated_dms'] or 0
        }
    }


def get_twitter_metrics(user_id: int, days: int = 30) -> dict:
    """Get Twitter/X specific metrics."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Twitter post stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_tweets,
                    COUNT(*) FILTER (WHERE p.status = 'posted') as successful_tweets,
                    COALESCE(SUM(p.likes), 0) as total_likes,
                    COALESCE(SUM(p.shares), 0) as total_retweets,
                    COALESCE(SUM(p.comments), 0) as total_replies_on_tweets,
                    COALESCE(SUM(p.views), 0) as total_impressions
                FROM posts p
                JOIN posts_accounts pa ON p.id = pa.post_id
                JOIN accounts a ON pa.account_id = a.id
                WHERE a.user_id = %s
                AND LOWER(a.platform) = 'twitter'
                AND p.created_at > NOW() - INTERVAL '%s days'
            """, (user_id, days))
            
            stats = cur.fetchone()
            
            # Get top performing tweets
            cur.execute("""
                SELECT
                    p.id,
                    p.title,
                    p.created_at,
                    p.likes,
                    p.shares as retweets,
                    p.comments as replies,
                    p.views as impressions,
                    a.account_username
                FROM posts p
                JOIN posts_accounts pa ON p.id = pa.post_id
                JOIN accounts a ON pa.account_id = a.id
                WHERE a.user_id = %s
                AND LOWER(a.platform) = 'twitter'
                AND p.status = 'posted'
                ORDER BY (p.likes + p.shares * 2 + p.comments * 1.5) DESC
                LIMIT 5
            """, (user_id,))
            
            top_tweets = cur.fetchall()
    
    total_tweets = stats['total_tweets'] or 0
    total_engagement = (stats['total_likes'] or 0) + (stats['total_retweets'] or 0) + (stats['total_replies_on_tweets'] or 0)
    
    return {
        "overview": {
            "total_tweets": total_tweets,
            "successful_tweets": stats['successful_tweets'] or 0,
            "success_rate": round(
                (stats['successful_tweets'] / total_tweets * 100) 
                if total_tweets > 0 else 0, 2
            )
        },
        "engagement": {
            "total_likes": stats['total_likes'] or 0,
            "total_retweets": stats['total_retweets'] or 0,
            "total_replies": stats['total_replies_on_tweets'] or 0,
            "total_impressions": stats['total_impressions'] or 0,
            "total_engagement": total_engagement,
            "avg_engagement_per_tweet": round(
                total_engagement / total_tweets 
                if total_tweets > 0 else 0, 2
            ),
            "engagement_rate": round(
                (total_engagement / (stats['total_impressions'] or 1)) * 100, 2
            ) if stats['total_impressions'] else 0
        },
        "top_tweets": [
            {
                "id": row["id"],
                "title": row["title"][:50] + "..." if row["title"] and len(row["title"]) > 50 else row["title"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "likes": row["likes"] or 0,
                "retweets": row["retweets"] or 0,
                "replies": row["replies"] or 0,
                "impressions": row["impressions"] or 0,
                "account": row["account_username"],
                "total_score": (row["likes"] or 0) + (row["retweets"] or 0) * 2 + (row["replies"] or 0) * 1.5
            }
            for row in top_tweets
        ]
    }


def get_conversation_stats(user_id: int, days: int = 30) -> dict:
    """Get conversation analytics."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Conversation overview
            cur.execute("""
                SELECT 
                    COUNT(DISTINCT dc.id) as total_conversations,
                    COUNT(DISTINCT dc.id) FILTER (
                        WHERE dc.last_message_at > NOW() - INTERVAL '7 days'
                    ) as active_last_7d,
                    COUNT(DISTINCT dc.id) FILTER (
                        WHERE dc.last_message_at > NOW() - INTERVAL '24 hours'
                    ) as active_last_24h,
                    COUNT(*) as total_messages,
                    COUNT(*) FILTER (WHERE dm.is_from_me = TRUE) as messages_sent,
                    COUNT(*) FILTER (WHERE dm.is_from_me = FALSE) as messages_received,
                    COUNT(*) FILTER (WHERE dm.ai_generated = TRUE) as ai_generated_messages,
                    MIN(dm.created_at) as first_message,
                    MAX(dm.created_at) as last_message
                FROM dm_conversations dc
                JOIN dm_messages dm ON dm.conversation_id = dc.id
                JOIN accounts a ON a.id = dc.account_id
                WHERE a.user_id = %s
                AND dm.created_at > NOW() - INTERVAL '%s days'
            """, (user_id, days))
            
            overview = cur.fetchone()
            
            # Top conversations by message count
            cur.execute("""
                SELECT 
                    dc.id,
                    dc.recipient_username,
                    COUNT(*) as message_count,
                    MAX(dm.created_at) as last_message,
                    COUNT(*) FILTER (WHERE dm.is_from_me = TRUE) as our_messages,
                    COUNT(*) FILTER (WHERE dm.ai_generated = TRUE) as ai_messages
                FROM dm_conversations dc
                JOIN dm_messages dm ON dm.conversation_id = dc.id
                JOIN accounts a ON a.id = dc.account_id
                WHERE a.user_id = %s
                AND dm.created_at > NOW() - INTERVAL '%s days'
                GROUP BY dc.id, dc.recipient_username
                ORDER BY message_count DESC
                LIMIT 10
            """, (user_id, days))
            
            top_conversations = cur.fetchall()
    
    total_messages = overview['total_messages'] or 0
    
    return {
        "overview": {
            "total_conversations": overview['total_conversations'] or 0,
            "active_last_7d": overview['active_last_7d'] or 0,
            "active_last_24h": overview['active_last_24h'] or 0,
            "total_messages": total_messages,
            "messages_sent": overview['messages_sent'] or 0,
            "messages_received": overview['messages_received'] or 0,
            "ai_generated_messages": overview['ai_generated_messages'] or 0,
            "first_message": overview['first_message'].isoformat() if overview['first_message'] else None,
            "last_message": overview['last_message'].isoformat() if overview['last_message'] else None,
            "ai_percentage": round(
                (overview['ai_generated_messages'] / total_messages * 100) 
                if total_messages > 0 else 0, 2
            )
        },
        "top_conversations": [
            {
                "conversation_id": row["id"],
                "recipient": row["recipient_username"],
                "message_count": row["message_count"],
                "last_message": row["last_message"].isoformat() if row["last_message"] else None,
                "our_messages": row["our_messages"],
                "ai_messages": row["ai_messages"],
                "ai_percentage": round((row["ai_messages"] / row["message_count"] * 100) if row["message_count"] > 0 else 0, 2)
            }
            for row in top_conversations
        ]
    }


def get_engagement_trends(user_id: int, days: int = 30) -> dict:
    """Get engagement trends over time."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Daily trends for last N days
            cur.execute("""
                WITH dates AS (
                    SELECT generate_series(
                        NOW() - INTERVAL '%s days',
                        NOW(),
                        '1 day'::interval
                    )::date AS date
                )
                SELECT 
                    d.date,
                    COALESCE(p.posts_count, 0) as posts,
                    COALESCE(c.comments_count, 0) as comments,
                    COALESCE(dm.dms_count, 0) as dms,
                    COALESCE(conv.messages_count, 0) as conversation_messages
                FROM dates d
                LEFT JOIN (
                    SELECT DATE(created_at) as date, COUNT(*) as posts_count
                    FROM posts
                    WHERE user_id = %s
                    GROUP BY DATE(created_at)
                ) p ON d.date = p.date
                LEFT JOIN (
                    SELECT DATE(created_at) as date, COUNT(*) as comments_count
                    FROM comment_jobs
                    WHERE user_id = %s
                    GROUP BY DATE(created_at)
                ) c ON d.date = c.date
                LEFT JOIN (
                    SELECT DATE(created_at) as date, COUNT(*) as dms_count
                    FROM dm_jobs
                    WHERE user_id = %s
                    GROUP BY DATE(created_at)
                ) dm ON d.date = dm.date
                LEFT JOIN (
                    SELECT DATE(dm.created_at) as date, COUNT(*) as messages_count
                    FROM dm_messages dm
                    JOIN dm_conversations dc ON dm.conversation_id = dc.id
                    JOIN accounts a ON a.id = dc.account_id
                    WHERE a.user_id = %s
                    GROUP BY DATE(dm.created_at)
                ) conv ON d.date = conv.date
                ORDER BY d.date DESC
            """, (days, user_id, user_id, user_id, user_id))
            
            trends = cur.fetchall()
    
    return {
        "daily": [
            {
                "date": row["date"].isoformat(),
                "posts": row["posts"],
                "comments": row["comments"],
                "dms": row["dms"],
                "conversation_messages": row["conversation_messages"],
                "total_activity": row["posts"] + row["comments"] + row["dms"] + row["conversation_messages"]
            }
            for row in trends
        ]
    }