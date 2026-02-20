#!/usr/bin/env python
# coding: utf-8

import psycopg2
import os
import time
import threading
import sys
import json
from datetime import datetime, timezone, timedelta
from google.oauth2.credentials import Credentials
import logging
from pathlib import Path
from google.auth.transport.requests import Request
from psycopg2.extras import RealDictCursor
import psycopg2.extras

APP_SCHEMA = "app"

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# PostgreSQL connection parameters
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


_db_lock = threading.Lock()

def connect():
    conn = psycopg2.connect(DATABASE_URL)
    # Set search_path to app schema for all queries
    with conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
    return conn


def get_db():
    """Database connection generator for FastAPI dependency"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize PostgreSQL database with schema"""
    # Use raw connection for init (schema may not exist yet)
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    c.execute("""
    CREATE SCHEMA IF NOT EXISTS app;
    """)

    # Set search_path so all tables are created in app schema
    # Include auth schema for foreign key references
    c.execute("SET search_path TO app, auth, public;")

    # ===========================================
    # MIGRATION: Consolidate to single auth.users
    # ===========================================

    # Check if app.users table exists and migrate FKs to auth.users
    c.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'app' AND table_name = 'users'
        );
    """)
    app_users_exists = c.fetchone()[0]

    if app_users_exists:
        # Drop foreign key constraints that reference app.users
        # Then drop the app.users table
        c.execute("""
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                -- Drop all FK constraints referencing app.users
                FOR r IN (
                    SELECT tc.constraint_name, tc.table_name, tc.table_schema
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.constraint_column_usage ccu
                        ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND ccu.table_schema = 'app'
                        AND ccu.table_name = 'users'
                ) LOOP
                    EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT IF EXISTS %I',
                        r.table_schema, r.table_name, r.constraint_name);
                END LOOP;
            END $$;
        """)

        # Drop the app.users table
        c.execute("DROP TABLE IF EXISTS app.users CASCADE;")
        conn.commit()

    # Groups table
    c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            group_name TEXT NOT NULL
        )
    """)


    # Migration: Add user_id column if missing
    c.execute("""
        ALTER TABLE groups
        ADD COLUMN IF NOT EXISTS user_id INTEGER;
    """)

    # Proxies table
    c.execute("""
        CREATE TABLE IF NOT EXISTS proxies (
            id SERIAL PRIMARY KEY,

            user_id INTEGER,
            proxy_address TEXT NOT NULL,
            proxy_type TEXT NOT NULL,

            is_active BOOLEAN NOT NULL DEFAULT TRUE,

            -- Health / diagnostics
            last_used TIMESTAMPTZ,
            fail_count INTEGER NOT NULL DEFAULT 0,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Migration: Add user_id column if missing
    c.execute("""
        ALTER TABLE proxies
        ADD COLUMN IF NOT EXISTS user_id INTEGER;
    """)

    # Accounts table
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            platform TEXT NOT NULL,
            account_username TEXT NOT NULL,
            password TEXT NOT NULL,
            session_data TEXT,
            status TEXT DEFAULT 'active'
        )
    """)

    # Migration: Add user_id column if missing
    c.execute("""
        ALTER TABLE accounts
        ADD COLUMN IF NOT EXISTS user_id INTEGER;
    """)

    # ===========================================
    # AI CLIP GENERATION TABLES
    # ===========================================
    c.execute("""
        CREATE TABLE IF NOT EXISTS clip_jobs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            source_url TEXT,
            local_video_path TEXT,
            clip_length INTEGER DEFAULT 30,
            max_clips INTEGER DEFAULT 3,
            style TEXT DEFAULT 'highlight',
            status TEXT NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    c.execute("""
        ALTER TABLE clip_jobs
        ADD COLUMN IF NOT EXISTS local_video_path TEXT;
    """)

    c.execute("""
        ALTER TABLE clip_jobs
        ADD COLUMN IF NOT EXISTS clip_length INTEGER DEFAULT 30;
    """)

    c.execute("""
        ALTER TABLE clip_jobs
        ADD COLUMN IF NOT EXISTS max_clips INTEGER DEFAULT 3;
    """)

    c.execute("""
        ALTER TABLE clip_jobs
        ADD COLUMN IF NOT EXISTS style TEXT DEFAULT 'highlight';
    """)

    c.execute("""
        ALTER TABLE clip_jobs
        ADD COLUMN IF NOT EXISTS error TEXT;
    """)


    c.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id SERIAL PRIMARY KEY,
            clip_job_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            duration INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (clip_job_id)
                REFERENCES clip_jobs(id)
                ON DELETE CASCADE
        );
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_clip_jobs_user
        ON clip_jobs (user_id);
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_clip_jobs_status
        ON clip_jobs (status);
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_clips_job
        ON clips (clip_job_id);
    """)

    # Posts table
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            media_file TEXT NOT NULL,
            title TEXT,
            description TEXT,
            hashtags TEXT,
            tags TEXT,
            privacy_status TEXT,
            scheduled_time TIMESTAMP WITH TIME ZONE,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            post_type TEXT DEFAULT 'feed',
            cover_image TEXT,
            audio_name TEXT,
            location TEXT,
            disable_comments BOOLEAN DEFAULT FALSE,
            share_to_feed BOOLEAN DEFAULT TRUE,
            user_id INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
    """)
    # ===============================
    # MIGRATION: Analytics fields
    # ===============================

    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS likes INTEGER NOT NULL DEFAULT 0;
    """)

    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS comments INTEGER NOT NULL DEFAULT 0;
    """)

    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS views INTEGER NOT NULL DEFAULT 0;
    """)

    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS shares INTEGER NOT NULL DEFAULT 0;
    """)

    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS error_message TEXT;
    """)
    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS youtube_video_id TEXT;
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_posts_youtube_video
        ON posts (youtube_video_id);
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_posts_user_status
        ON posts (user_id, status);
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_posts_created_at
        ON posts (created_at);
    """)



    # Migration: Add user_id column if missing
    c.execute("""
        ALTER TABLE posts
        ADD COLUMN IF NOT EXISTS user_id INTEGER;
    """)

    # Group ↔ Account mapping table
    c.execute("""
        CREATE TABLE IF NOT EXISTS group_accounts (
            group_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            PRIMARY KEY (group_id, account_id),
            FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
    """)

    # Tokens table
    c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at BIGINT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
    """)

    # Table to associate posts with multiple accounts
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts_accounts (
            post_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            proxy_id INTEGER,
            PRIMARY KEY (post_id, account_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(proxy_id) REFERENCES proxies(id) ON DELETE SET NULL
        )
    """)
    
    # Timezones table
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_timezones (
            user_id INTEGER PRIMARY KEY,
            timezone TEXT NOT NULL DEFAULT 'UTC'
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_posts_scheduled
    ON posts (status, scheduled_time);
    """)

    # APScheduler job store table
    c.execute("""
        CREATE TABLE IF NOT EXISTS apscheduler_jobs (
            id TEXT PRIMARY KEY,
            next_run_time DOUBLE PRECISION,
            job_state BYTEA NOT NULL
        )
    """)

     # ===========================================
    # MESSAGING SYSTEM TABLES
    # ===========================================
    
    # Conversations table
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMPTZ
        );
    """)
    
    # Conversation participants (many-to-many)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversation_participants (
            conversation_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (conversation_id, user_id),
            FOREIGN KEY (conversation_id) 
                REFERENCES conversations(id) 
                ON DELETE CASCADE,
            FOREIGN KEY (user_id) 
                REFERENCES auth.users(id) 
                ON DELETE CASCADE
        );
    """)
    
    # Messages table
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            FOREIGN KEY (conversation_id) 
                REFERENCES conversations(id) 
                ON DELETE CASCADE,
            FOREIGN KEY (sender_id) 
                REFERENCES auth.users(id) 
                ON DELETE CASCADE
        );
    """)
    
    # Indexes for performance
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_conversation 
        ON messages (conversation_id, created_at DESC);
    """)
    
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_participants_user 
        ON conversation_participants (user_id);
    """)
    
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_unread 
        ON messages (conversation_id, is_read) 
        WHERE is_read = FALSE;
    """)

    conn.commit()
    conn.close()

# Account operations
def add_account(user_id, platform, account_username, password):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO accounts (user_id, platform, account_username, password)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (user_id, platform, account_username, password))
        conn.commit()
        return c.fetchone()[0]
    finally:
        conn.close()

def delete_account(account_id):
    """Delete an account from the database"""
    conn = connect()
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
    conn.commit()
    conn.close()

def get_accounts(user_id):
    conn = connect()
    c = conn.cursor()
    c.execute("""
        SELECT
            a.id,
            a.platform,
            a.account_username,
            a.password
        FROM accounts a
        WHERE a.user_id = %s
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_accounts_by_filters(
    user_id,
    platform=None,
    group_id=None,
    group_name=None,
    return_dict=False
):
    conn = connect()
    c = conn.cursor()

    query = """
        SELECT
            a.id,
            a.platform,
            a.account_username,
            a.password,
            g.id AS group_id,
            g.group_name
        FROM accounts a
        LEFT JOIN group_accounts ga ON ga.account_id = a.id
        LEFT JOIN groups g ON g.id = ga.group_id
        WHERE a.user_id = %s
    """
    params = [user_id]

    if platform:
        query += " AND a.platform = %s"
        params.append(platform)

    if group_id is not None:
        query += " AND g.id = %s"
        params.append(group_id)
    elif group_name is not None:
        query += " AND g.group_name = %s"
        params.append(group_name)

    c.execute(query, tuple(params))
    results = c.fetchall()
    conn.close()

    if return_dict:
        return [
            {
                "id": row[0],
                "platform": row[1],
                "account_username": row[2],
                "password": row[3],
                "group_id": row[4],
                "group_name": row[5],
            }
            for row in results
        ]

    return results

def get_account_by_id(account_id, user_id):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, platform, account_username
            FROM accounts
            WHERE id = %s AND user_id = %s
        """, (account_id, user_id))
        return c.fetchone()
    finally:
        conn.close()

def add_account_to_group(group_id, account_id):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO group_accounts (group_id, account_id)
            VALUES (%s, %s)
            ON CONFLICT (group_id, account_id) DO NOTHING
        """, (group_id, account_id))
        conn.commit()
    finally:
        conn.close()

def remove_account_from_group(group_id, account_id):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            DELETE FROM group_accounts
            WHERE group_id = %s AND account_id = %s
        """, (group_id, account_id))
        conn.commit()
    finally:
        conn.close()

def get_accounts_for_group(group_id, user_id):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT a.id, a.platform, a.account_username
            FROM accounts a
            JOIN group_accounts ga ON ga.account_id = a.id
            WHERE ga.group_id = %s AND a.user_id = %s
        """, (group_id, user_id))
        return c.fetchall()
    finally:
        conn.close()

def get_available_accounts_for_group(group_id, user_id):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT a.id, a.platform, a.account_username
            FROM accounts a
            WHERE a.user_id = %s
            AND a.id NOT IN (
                SELECT account_id
                FROM group_accounts
                WHERE group_id = %s
            )
        """, (user_id, group_id))
        return c.fetchall()
    finally:
        conn.close()

def get_all_accounts_with_groups(user_id):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT
                a.id,
                a.platform,
                a.account_username,
                g.id AS group_id,
                g.group_name
            FROM accounts a
            LEFT JOIN group_accounts ga ON ga.account_id = a.id
            LEFT JOIN groups g ON g.id = ga.group_id
            WHERE a.user_id = %s
        """, (user_id,))
        return c.fetchall()
    finally:
        conn.close()

# Post operations
def add_post(
    user_id: int,
    account_ids,
    filename,
    title=None,
    description=None,
    hashtags=None,
    tags=None,
    privacy_status=None,
    scheduled_time=None,
    post_type="feed",
    cover_image=None,
    audio_name=None,
    location=None,
    disable_comments=False,
    share_to_feed=True,
):
    if not isinstance(account_ids, list) or not account_ids:
        raise ValueError("account_ids must be a non-empty list")

    conn = connect()
    cur = conn.cursor()

    try:
        tags_str = ",".join(tags) if isinstance(tags, list) else (tags or "")
        
        # Handle scheduled_time for PostgreSQL
        scheduled_iso = None
        if scheduled_time:
            if isinstance(scheduled_time, datetime):
                scheduled_iso = scheduled_time.astimezone(timezone.utc)
            else:
                scheduled_iso = scheduled_time

        cur.execute("""
            INSERT INTO posts (
                user_id,
                account_id,
                media_file,
                title,
                description,
                hashtags,
                tags,
                privacy_status,
                scheduled_time,
                post_type,
                cover_image,
                audio_name,
                location,
                disable_comments,
                share_to_feed,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
            RETURNING id
        """, (
            user_id,
            account_ids[0],  # legacy compatibility only
            filename,
            title or "",
            description or "",
            hashtags or "",
            tags_str,
            privacy_status,
            scheduled_iso,
            post_type,
            cover_image,
            audio_name,
            location,
            disable_comments,
            share_to_feed,
        ))

        post_id = cur.fetchone()[0]

        for acc_id in account_ids:
            cur.execute(
                "INSERT INTO posts_accounts (post_id, account_id) VALUES (%s, %s)",
                (post_id, acc_id)
            )

        conn.commit()
        return post_id

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_post_details_by_post_id(post_id: int):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            p.id,
            p.user_id,
            p.media_file,
            p.title,
            p.description,
            p.hashtags,
            p.tags,
            p.privacy_status,
            p.post_type,
            p.cover_image,
            p.audio_name,
            p.location,
            p.disable_comments,
            p.share_to_feed,
            p.status,
            p.created_at
        FROM posts p
        WHERE p.id = %s
        """,
        (post_id,),
    )

    post_row = cursor.fetchone()
    if not post_row:
        conn.close()
        return None

    (
        post_id,
        user_id,
        media_file,
        title,
        description,
        hashtags,
        tags,
        privacy_status,
        post_type,
        cover_image,
        audio_name,
        location,
        disable_comments,
        share_to_feed,
        status,
        created_at,
    ) = post_row

    # Fetch linked accounts
    cursor.execute(
        """
        SELECT
            a.id,
            a.platform,
            a.account_username
        FROM posts_accounts pa
        JOIN accounts a ON a.id = pa.account_id
        WHERE pa.post_id = %s
        """,
        (post_id,),
    )

    accounts = [
        {
            "id": row[0],
            "platform": row[1],
            "username": row[2],
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return {
        "id": post_id,
        "user_id": user_id,
        "media_file": media_file,
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "tags": tags,
        "privacy_status": privacy_status,
        "post_type": post_type,
        "cover_image": cover_image,
        "audio_name": audio_name,
        "location": location,
        "disable_comments": bool(disable_comments),
        "share_to_feed": bool(share_to_feed),
        "status": status,
        "created_at": created_at,
        "accounts": accounts,
    }

def get_scheduled_posts():
    """Get posts that are scheduled and pending (including past due)"""
    conn = connect()
    c = conn.cursor()
    c.execute("""
        SELECT id, account_id, media_file, title, description, 
               hashtags, scheduled_time, status
        FROM posts
        WHERE scheduled_time IS NOT NULL 
        AND status = 'Pending'
        ORDER BY scheduled_time DESC 
    """)
    posts = c.fetchall()
    conn.close()
    return posts

def get_accounts_by_post_id(post_id):
    """
    Returns list of account dictionaries with group info
    """
    conn = connect()
    c = conn.cursor()
    c.execute("""
        SELECT
            a.id,
            a.platform,
            a.account_username,
            a.password,
            g.id AS group_id,
            g.group_name
        FROM accounts a
        JOIN posts_accounts pa ON a.id = pa.account_id
        LEFT JOIN group_accounts ga ON ga.account_id = a.id
        LEFT JOIN groups g ON g.id = ga.group_id
        WHERE pa.post_id = %s
    """, (post_id,))

    accounts = []
    for row in c.fetchall():
        accounts.append({
            "id": row[0],
            "platform": row[1],
            "account_username": row[2],
            "password": row[3],
            "group_id": row[4],
            "group_name": row[5],
        })

    conn.close()
    return accounts

def update_post_status(post_id, status, error_message=None):
    with _db_lock:
        conn = connect()
        c = conn.cursor()

        c.execute("""
            UPDATE posts
            SET 
                status = %s,
                error_message = %s
            WHERE id = %s
        """, (status, error_message, post_id))

        conn.commit()
        conn.close()

    logger.info(f"Post {post_id} status → {status}")


def update_post_schedule_time(post_id, scheduled_time):
    conn = connect()
    c = conn.cursor()
    c.execute("UPDATE posts SET scheduled_time = %s WHERE id = %s", (scheduled_time, post_id))
    conn.commit()
    conn.close()

def get_groups(user_id: int):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT id, group_name
            FROM groups
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,),
        )
        return c.fetchall()
    finally:
        conn.close()


def add_group(group_name):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO groups (group_name) VALUES (%s)", (group_name,))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        return False
    finally:
        conn.close()

def parse_datetime(dt_str):
    """Safely parse datetime string with timezone handling"""
    if not dt_str:
        return None
    try:
        # Handle ISO format with timezone
        if 'Z' in dt_str:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        elif '+' in dt_str or '-' in dt_str:
            return datetime.fromisoformat(dt_str)
        else:
            # Assume naive datetime is in UTC
            return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error(f"Failed to parse datetime string: {dt_str}")
        return None

def get_post_status_by_id(post_id):
    """Get current status of a post"""
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT status FROM posts WHERE id = %s", (post_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_posts_for_user(user_id: int):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT DISTINCT
            p.id,
            p.title,
            p.description,
            p.status,
            p.created_at,
            p.scheduled_time
        FROM posts p
        WHERE p.user_id = %s
        ORDER BY p.created_at DESC
        """,
        (user_id,),
    )

    posts = cursor.fetchall()
    results = []

    for row in posts:
        post_id = row[0]

        cursor.execute(
            """
            SELECT
                a.id,
                a.platform,
                a.account_username
            FROM posts_accounts pa
            JOIN accounts a ON a.id = pa.account_id
            WHERE pa.post_id = %s
            """,
            (post_id,),
        )

        accounts = [
            {
                "id": acc[0],
                "platform": acc[1],
                "username": acc[2],
            }
            for acc in cursor.fetchall()
        ]

        results.append(
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "status": row[3],
                "created_at": row[4],
                "scheduled_time": row[5],
                "accounts": accounts,
            }
        )

    conn.close()
    return results

def get_due_posts():
    """
    Returns posts that should be executed now
    """
    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT
            p.id,
            p.user_id,
            p.account_id,
            p.media_file,
            p.title,
            p.description,
            p.hashtags,
            p.scheduled_time,
            p.status
        FROM posts p
        WHERE
            p.status = 'Pending'
            AND p.scheduled_time IS NOT NULL
            AND p.scheduled_time <= NOW()
        ORDER BY p.scheduled_time ASC
    """)

    posts = c.fetchall()
    conn.close()
    return posts

def update_matching_posts_status(reference_post_id, status):
    """
    Update status for all posts that match the reference post's:
    - media_file
    - scheduled_time
    - created_at (within 1 minute window)
    """
    conn = connect()
    c = conn.cursor()
    try:
        # First get the reference post details
        c.execute("""
            SELECT media_file, scheduled_time, created_at 
            FROM posts 
            WHERE id = %s
        """, (reference_post_id,))
        ref_post = c.fetchone()
        
        if not ref_post:
            logger.error(f"Reference post {reference_post_id} not found")
            return False
            
        media_file, scheduled_time, created_at = ref_post
        
        # Update all matching posts
        c.execute("""
            UPDATE posts 
            SET status = %s
            WHERE media_file = %s
            AND scheduled_time = %s
            AND ABS(EXTRACT(EPOCH FROM created_at) - EXTRACT(EPOCH FROM %s)) <= 60
            AND status != %s
        """, (
            status,
            media_file,
            scheduled_time,
            created_at,
            status
        ))
        
        updated_count = c.rowcount
        conn.commit()
        logger.info(f"Updated {updated_count} posts to status '{status}' for media {media_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating matching posts: {e}")
        return False
    finally:
        conn.close()

def get_instagram_credentials(account_id: int):
    """
    Fetch Instagram credentials (username, password, session)
    for a given account ID.
    """
    conn = connect()
    c = conn.cursor()

    try:
        c.execute("""
            SELECT
                account_username,
                password,
                session_data
            FROM accounts
            WHERE id = %s
              AND LOWER(platform) = 'instagram'
        """, (account_id,))

        row = c.fetchone()

        if not row:
            logger.error(f"[INSTAGRAM] No Instagram account found for account_id={account_id}")
            return None

        username, password, session_data = row

        return {
            "username": username,
            "password": password,
            "session": json.loads(session_data) if session_data else None,
        }

    except Exception as e:
        logger.error(
            f"[INSTAGRAM] Failed to fetch credentials for account_id={account_id}: {e}",
            exc_info=True
        )
        return None

    finally:
        conn.close()

def update_instagram_session(account_id: int, session: dict):
    """
    Persist updated instagrapi session to DB.
    """
    conn = connect()
    c = conn.cursor()

    c.execute("""
        UPDATE accounts
        SET session_data = %s
        WHERE id = %s
          AND LOWER(platform) = 'instagram'
    """, (json.dumps(session), account_id))

    conn.commit()
    conn.close()

# Function to load the client secrets from the 'client_secret.json'
def get_client_secret_data():
    BASE_DIR = Path(__file__).parent
    CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
    
    with open(CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    
    client_id = data['installed']['client_id']
    client_secret = data['installed']['client_secret']
    token_uri = data['installed']['token_uri']
    
    return client_id, client_secret, token_uri

def get_posts(user_id):
    """Get all posts for a user, including scheduled and posted"""
    conn = connect()
    c = conn.cursor()
    c.execute("""
        SELECT p.id, p.account_id, p.media_file, p.title, p.description, 
               p.hashtags, p.scheduled_time, p.status, a.platform
        FROM posts p
        JOIN accounts a ON p.account_id = a.id
        WHERE a.user_id = %s
        ORDER BY p.id DESC 
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_random_proxy(user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, proxy_address, proxy_type
        FROM proxies
        WHERE is_active = TRUE
          AND user_id = %s
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (user_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row  # (id, address, type) or None



def post_with_random_proxy(user_id, account_id, media_path, caption, post_id):
    proxy = get_random_proxy(user_id)
    if not proxy:
        raise Exception("No active proxies available")

    proxy_id, proxy_address, proxy_type = proxy

    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            UPDATE posts_accounts
            SET proxy_id = %s
            WHERE account_id = %s
              AND post_id = %s
            """,
            (proxy_id, account_id, post_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "proxy_id": proxy_id,
        "proxy_address": proxy_address,
        "proxy_type": proxy_type,
    }


# Proxy operations
def add_proxy(proxy_address: str, proxy_type: str, user_id: int):
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO proxies (proxy_address, proxy_type, user_id)
            VALUES (%s, %s, %s)
            """,
            (proxy_address, proxy_type, user_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def get_all_proxies(user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, proxy_address, proxy_type, is_active
        FROM proxies
        WHERE user_id = %s
        ORDER BY id DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def update_proxy_status(proxy_id: int, is_active: bool, user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE proxies
        SET is_active = %s
        WHERE id = %s AND user_id = %s
        """,
        (is_active, proxy_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_proxy(proxy_id: int, user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM proxies
        WHERE id = %s AND user_id = %s
        """,
        (proxy_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()

def get_proxy_by_id(proxy_id: int, user_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, proxy_address, proxy_type, is_active
        FROM proxies
        WHERE id = %s AND user_id = %s
        """,
        (proxy_id, user_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def set_user_timezone(user_id, timezone):
    """Set a user's preferred timezone"""
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO user_timezones (user_id, timezone)
            VALUES (%s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET timezone = EXCLUDED.timezone
        """, (user_id, timezone))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting timezone: {e}")
        return False
    finally:
        conn.close()

def get_user_timezone(user_id):
    """Get a user's preferred timezone"""
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("SELECT timezone FROM user_timezones WHERE user_id = %s", (user_id,))
        row = c.fetchone()
        return row[0] if row else 'UTC'
    except Exception as e:
        logger.error(f"Error getting timezone: {e}")
        return 'UTC'
    finally:
        conn.close()

def reset_post_for_repost(post_id: int):
    """
    Reset a post so it can be re-executed safely.
    Keeps media_file and account mappings intact.
    """
    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            UPDATE posts
            SET status = 'Pending'
            WHERE id = %s
            """,
            (post_id,),
        )

        if c.rowcount == 0:
            raise ValueError("Post not found")

        conn.commit()
        logger.info(f"[DB] Post {post_id} reset to Pending for repost")

    finally:
        conn.close()

def get_all_youtube_accounts_with_tokens():
    """
    Returns all YouTube accounts with their OAuth tokens.
    """
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            a.id AS account_id,
            t.access_token,
            t.refresh_token,
            t.expires_at
        FROM accounts a
        JOIN tokens t ON t.account_id = a.id
        WHERE LOWER(a.platform) = 'youtube'
    """)

    rows = cur.fetchall()
    conn.close()

    return [
        {
            "account_id": row[0],
            "access_token": row[1],
            "refresh_token": row[2],
            "expires_at": row[3],
        }
        for row in rows
    ]


def update_youtube_tokens(account_id: int, access_token: str, expires_at: int):
    """
    Update OAuth tokens for a YouTube account.
    expires_at is epoch seconds.
    """
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        UPDATE tokens
        SET
            access_token = %s,
            expires_at = %s
        WHERE account_id = %s
    """, (access_token, expires_at, account_id))

    conn.commit()
    conn.close()


def create_clip_job(
    user_id: int,
    source_url: str | None,
    local_video_path: str | None,
    clip_length: int,
    max_clips: int,
    style: str,
) -> int:
    conn = connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO clip_jobs (
                user_id,
                source_url,
                local_video_path,
                clip_length,
                max_clips,
                style,
                status,
                progress
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', 0)
            RETURNING id;
            """,
            (
                user_id,
                source_url,
                local_video_path,
                clip_length,
                max_clips,
                style,
            ),
        )

        job_id = c.fetchone()[0]
        conn.commit()
        return job_id
    finally:
        conn.close()



def update_clip_job_status(
    job_id: int,
    status: str,
    progress: int | None = None,
    error: str | None = None,
):
    conn = connect()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE clip_jobs
            SET
                status = %s,
                progress = COALESCE(%s, progress),
                error = %s
            WHERE id = %s;
        """, (status, progress, error, job_id))

        conn.commit()
    finally:
        conn.close()

def mark_clip_job_failed(job_id: int, error: str):
    update_clip_job_status(
        job_id=job_id,
        status="failed",
        progress=0,
        error=error[:1000],
    )

def get_clip_job(job_id: int):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT
            id,
            user_id,
            source_url,
            local_video_path,
            clip_length,
            max_clips,
            style,
            status,
            progress,
            error,
            created_at
        FROM clip_jobs
        WHERE id = %s;
    """, (job_id,))

    row = c.fetchone()

    c.close()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "user_id": row[1],
        "source_url": row[2],
        "local_video_path": row[3],
        "clip_length": row[4],
        "max_clips": row[5],
        "style": row[6],
        "status": row[7],
        "progress": row[8],
        "error": row[9],
        "created_at": row[10],
    }


def add_clip(clip_job_id: int, file_path: str, duration: int) -> int:
    """
    Insert a generated clip into the database.
    """

    conn = connect()
    c = conn.cursor()

    c.execute("""
        INSERT INTO clips (clip_job_id, file_path, duration)
        VALUES (%s, %s, %s)
        RETURNING id;
    """, (clip_job_id, file_path, duration))

    clip_id = c.fetchone()[0]

    conn.commit()
    c.close()
    conn.close()

    return clip_id



def get_clips_for_job(job_id: int):
    """
    Return all clips for a job.
    """

    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT
            id,
            clip_job_id,
            file_path,
            duration,
            created_at
        FROM clips
        WHERE clip_job_id = %s
        ORDER BY created_at ASC;
    """, (job_id,))

    rows = c.fetchall()

    c.close()
    conn.close()

    clips = []

    for row in rows:
        clips.append({
            "id": row[0],
            "job_id": row[1],  # keeping API output consistent
            "file_path": row[2],
            "duration": row[3],
            "created_at": row[4],
        })

    return clips



def delete_clips_for_job(job_id: int):
    """
    Delete all clips belonging to a job.
    """

    conn = connect()
    c = conn.cursor()

    c.execute("""
        DELETE FROM clips
        WHERE clip_job_id = %s;
    """, (job_id,))

    conn.commit()
    c.close()
    conn.close()


def get_clip_job_with_clips(job_id: int):
    job = get_clip_job(job_id)
    if not job:
        return None

    job["clips"] = get_clips_for_job(job_id)
    return job


from typing import List
def get_all_clip_jobs_for_user(user_id: int) -> List[dict]:
    """Get all clip jobs for a user"""
    conn = connect()
    c = conn.cursor()
    
    c.execute("""
        SELECT
            id,
            user_id,
            source_url,
            local_video_path,
            clip_length,
            max_clips,
            style,
            status,
            progress,
            error,
            created_at
        FROM clip_jobs
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))
    
    rows = c.fetchall()
    conn.close()
    
    jobs = []
    for row in rows:
        jobs.append({
            "id": row[0],
            "user_id": row[1],
            "source_url": row[2],
            "local_video_path": row[3],
            "clip_length": row[4],
            "max_clips": row[5],
            "style": row[6],
            "status": row[7],
            "progress": row[8],
            "error": row[9],
            "created_at": row[10],
        })
    
    return jobs

def delete_clip_job_and_clips(job_id: int):
    """Delete a clip job and all its clips from database"""
    conn = connect()
    c = conn.cursor()
    
    # Clips will be deleted automatically due to CASCADE
    c.execute("DELETE FROM clip_jobs WHERE id = %s", (job_id,))
    
    conn.commit()
    conn.close()

def get_post_overview(user_id: int):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(*) as total_posts,
            COUNT(*) FILTER (WHERE status = 'Success') as successful_posts,
            COUNT(*) FILTER (WHERE status = 'Failed') as failed_posts
        FROM posts
        WHERE user_id = %s
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    total = row[0] or 0
    success = row[1] or 0
    failed = row[2] or 0

    success_rate = (success / total * 100) if total > 0 else 0

    return {
        "total_posts": total,
        "successful_posts": success,
        "failed_posts": failed,
        "success_rate": round(success_rate, 2)
    }


def get_platform_breakdown(user_id: int):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            a.platform,
            COUNT(*) FILTER (WHERE p.status = 'Success') as success_count,
            COUNT(*) FILTER (WHERE p.status = 'Failed') as failed_count
        FROM posts p
        JOIN posts_accounts pa ON p.id = pa.post_id
        JOIN accounts a ON pa.account_id = a.id
        WHERE p.user_id = %s
        GROUP BY a.platform
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    results = {}
    for platform, success, failed in rows:
        total = (success or 0) + (failed or 0)

        results[platform.lower()] = {
            "success": success or 0,
            "failed": failed or 0,
            "success_rate": round((success / total * 100), 2) if total > 0 else 0
        }

    return results



def get_daily_post_counts(user_id: int):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            DATE(created_at) as post_date,
            COUNT(*) as count
        FROM posts
        WHERE user_id = %s
        GROUP BY post_date
        ORDER BY post_date ASC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {"date": str(row[0]), "count": row[1]}
        for row in rows
    ]

def update_post_engagement(post_id: int, likes: int = 0, comments: int = 0, views: int = 0, shares: int = 0):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        UPDATE posts
        SET 
            likes = %s,
            comments = %s,
            views = %s,
            shares = %s
        WHERE id = %s
    """, (likes, comments, views, shares, post_id))

    conn.commit()
    conn.close()


def get_engagement_stats(user_id: int):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COALESCE(SUM(likes), 0),
            COALESCE(SUM(comments), 0),
            COALESCE(SUM(views), 0),
            COALESCE(SUM(shares), 0)
        FROM posts
        WHERE user_id = %s
        AND status = 'Success'
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    total_likes, total_comments, total_views, total_shares = row

    total_posts_query = get_post_overview(user_id)
    total_posts = total_posts_query["successful_posts"]

    engagement_rate = (
        (total_likes + total_comments + total_shares) / total_posts
        if total_posts > 0 else 0
    )

    return {
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_views": total_views,
        "total_shares": total_shares,
        "engagement_rate": round(engagement_rate, 2)
    }


def calculate_account_health(user_id: int):
    overview = get_post_overview(user_id)
    platform = get_platform_breakdown(user_id)

    score = 0
    issues = []

    # 40% based on success rate
    score += overview["success_rate"] * 0.4

    if overview["success_rate"] < 70:
        issues.append("Low success rate")

    # Platform penalties
    for p in platform.values():
        if p["success_rate"] < 60:
            score -= 5
            issues.append("High failure rate on platform")

    score = max(0, min(100, score))

    if score >= 80:
        status = "Excellent"
    elif score >= 60:
        status = "Good"
    elif score >= 40:
        status = "Fair"
    else:
        status = "Poor"

    return {
        "score": round(score),
        "status": status,
        "issues": issues
    }


def save_youtube_video_id(post_id: int, video_id: str):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        UPDATE posts
        SET youtube_video_id = %s
        WHERE id = %s
    """, (video_id, post_id))

    conn.commit()
    conn.close()

def get_youtube_posts_with_tokens():
    """
    Returns posts that have a YouTube video ID
    along with OAuth tokens for API calls.
    """

    conn = connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            p.id,
            p.youtube_video_id,
            t.access_token,
            t.refresh_token,
            t.expires_at
        FROM posts p
        JOIN posts_accounts pa ON p.id = pa.post_id
        JOIN accounts a ON pa.account_id = a.id
        JOIN tokens t ON t.account_id = a.id
        WHERE LOWER(a.platform) = 'youtube'
        AND p.youtube_video_id IS NOT NULL
        AND p.status = 'posted'
        AND p.created_at >= NOW() - INTERVAL '30 days'

    """)

    rows = cur.fetchall()
    conn.close()

    return [
        {
            "post_id": row[0],
            "video_id": row[1],
            "access_token": row[2],
            "refresh_token": row[3],
            "expires_at": row[4],
        }
        for row in rows
    ]
