import psycopg2
import psycopg2.extras
import json
import os
import sqlite3
from datetime import datetime, timedelta
import threading
from typing import Optional
from urllib.parse import urlparse

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.config import settings
from app.utils.security import verify_password

import uuid

AUTH_SCHEMA = "auth"

# --------------------------------------------------
# CONNECTION
# --------------------------------------------------

_DB_LOCK = threading.Lock()

#  Hosted

def get_conn():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    result = urlparse(database_url)

    conn = psycopg2.connect(
        dbname=result.path.lstrip("/"),
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    # Set search_path to auth schema for all queries
    with conn.cursor() as cur:
        cur.execute("SET search_path TO auth, public;")
    return conn



def init_auth_db():
    # Use raw connection for init (schema may not exist yet)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    result = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=result.path.lstrip("/"),
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )

    with conn:
        with conn.cursor() as cur:

            cur.execute("""
            CREATE SCHEMA IF NOT EXISTS auth;
            """)

            # Set search_path so all tables are created in auth schema
            cur.execute("SET search_path TO auth, public;")

            # USERS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,

                    -- Admin & lifecycle control
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    disabled_at TIMESTAMPTZ,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

            """)

            # YOUTUBE TOKENS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS youtube_tokens (
                    account_id INTEGER PRIMARY KEY,
                    token_json JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # SUBSCRIPTION PLANS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    max_channels INTEGER NOT NULL,
                    posts_per_day INTEGER NOT NULL,
                    comments_per_day INTEGER NOT NULL,
                    dms_per_day INTEGER NOT NULL,
                    duration_days INTEGER NOT NULL DEFAULT 30,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # USER SUBSCRIPTIONS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    plan_id INTEGER NOT NULL
                        REFERENCES subscription_plans(id)
                        ON DELETE RESTRICT,
                    start_date TIMESTAMPTZ NOT NULL,
                    end_date TIMESTAMPTZ NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # DAILY USAGE COUNTERS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usage_counters (
                    user_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    date DATE NOT NULL,
                    posts INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    dms INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, platform, date)
                );
            """)

            # SEED PLANS
            cur.execute("""
                INSERT INTO subscription_plans
                    (name, max_channels, posts_per_day, comments_per_day, dms_per_day)
                VALUES
                    ('Tier 1', 3, 9, 9, 9),
                    ('Tier 2', 10, 30, 30, 30),
                    ('Tier 3', 100, 300, 300, 300),
                    ('Tier 4', 1000, 3000, 3000, 3000),
                    ('Tier 5 (Enterprise)', 10000, 30000, 30000, 30000)
                ON CONFLICT (name) DO NOTHING;
            """)

            # PAYMENT INTENTS & EVENTS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payment_intents (
                    id UUID PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    plan_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT DEFAULT 'KES',
                    status TEXT NOT NULL DEFAULT 'pending',
                    zeroid_reference TEXT UNIQUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS payment_events (
                    id SERIAL PRIMARY KEY,
                    payment_intent_id UUID NOT NULL,
                    event_type TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    received_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """)

            cur.execute("""
            CREATE INDEX idx_password_reset_token ON password_reset_tokens(token);
            """)


        conn.commit()



# --------------------------------------------------
# USERS
# --------------------------------------------------

def add_user(email: str, password_hash: str) -> Optional[int]:
    """
    Creates a user in auth.users
    AND mirrors the user into app.users.

    Returns user_id on success, None if user already exists.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 1️⃣ Insert into auth.users
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (email, password_hash),
                )

                user_id = cur.fetchone()["id"]

                cur.execute(
                    """
                    INSERT INTO app.users (id)
                    VALUES (%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id,),
                )

            conn.commit()
            return user_id

    except psycopg2.errors.UniqueViolation:
        return None



def verify_user(username: str, password: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT password_hash, is_active
                FROM users
                WHERE email = %s
                """,
                (username,),
            )
            row = cur.fetchone()

    if not row or not row["is_active"]:
        return False

    return verify_password(password, row["password_hash"])



def get_user_by_email(email: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email FROM users WHERE email = %s",
                (email,),
            )
            return cur.fetchone()


# --------------------------------------------------
# YOUTUBE TOKENS (SINGLE SOURCE OF TRUTH)
# --------------------------------------------------

def store_token_in_db(account_id: int, creds: Credentials) -> None:
    """
    Atomic upsert to avoid race conditions.
    Stores the FULL credential state.

    HARD RULE:
    - creds.expiry is ALWAYS stored as NAIVE UTC
    """
    expiry = None
    if creds.expiry:
        expiry = creds.expiry
        if expiry.tzinfo is not None:
            expiry = expiry.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
        "expiry": expiry.isoformat() if expiry else None,
    }

    with _DB_LOCK:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO youtube_tokens (account_id, token_json, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (account_id)
                    DO UPDATE SET
                        token_json = EXCLUDED.token_json,
                        updated_at = NOW()
                    """,
                    (account_id, json.dumps(token_data)),
                )


def _load_youtube_credentials(account_id: int) -> Optional[Credentials]:
    """
    INTERNAL helper.
    Loads credentials from Postgres without refreshing.

    GUARANTEE:
    - creds.expiry is ALWAYS naive UTC
    - Safe for Google SDK + FastAPI + Celery
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT token_json
                FROM youtube_tokens
                WHERE account_id = %s
                """,
                (account_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    token_data = row["token_json"]

    if isinstance(token_data, str):
        token_data = json.loads(token_data)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    expiry_str = token_data.get("expiry")
    if expiry_str:
        expiry = datetime.fromisoformat(expiry_str)

        # FORCE naive UTC (no exceptions)
        if expiry.tzinfo is not None:
            expiry = expiry.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        creds.expiry = expiry

    return creds


def get_valid_youtube_token(account_id: int) -> Optional[Credentials]:
    """
    Returns a VALID YouTube Credentials object.

    SAFE FOR:
    - FastAPI requests
    - Celery workers
    - Google Credentials internals

    CONTRACT:
    - All datetime comparisons are NAIVE UTC
    """
    creds = _load_youtube_credentials(account_id)
    if not creds:
        return None

    now = datetime.utcnow()  # NAIVE UTC (matches Google internals)

    needs_refresh = (
        not creds.valid
        or (
            creds.expiry
            and creds.expiry <= now + timedelta(minutes=5)
        )
    )

    if needs_refresh:
        if not creds.refresh_token:
            raise RuntimeError(
                f"YouTube token for account {account_id} has no refresh token"
            )

        creds.refresh(Request())
        store_token_in_db(account_id, creds)

    return creds



def refresh_youtube_token_now(account_id: int) -> bool:
    """
    OPTIONAL utility function.

    Forces a refresh immediately.
    Returns True if refreshed, False if token does not exist.
    """
    creds = _load_youtube_credentials(account_id)
    if not creds:
        return False

    if not creds.refresh_token:
        raise RuntimeError(
            f"YouTube token for account {account_id} has no refresh token"
        )

    creds.refresh(Request())
    store_token_in_db(account_id, creds)
    return True

def get_active_subscription(conn, user_id: int):
    now = datetime.utcnow()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                us.plan_id,
                sp.name AS plan_name,
                us.start_date,
                us.end_date,
                us.is_active,
                'active' AS status,
                sp.max_channels,
                sp.posts_per_day,
                sp.comments_per_day,
                sp.dms_per_day
            FROM user_subscriptions us
            JOIN subscription_plans sp ON sp.id = us.plan_id
            WHERE us.user_id = %s
              AND us.is_active = TRUE
              AND us.start_date <= %s
              AND us.end_date >= %s
        """, (user_id, now, now))

        return cur.fetchone()


def require_active_subscription(conn, user_id: int):
    plan = get_active_subscription(conn, user_id)
    if not plan:
        raise PermissionError("No active subscription")
    return plan


def _today():
    return datetime.utcnow().date()


def get_today_usage(conn, user_id, platform):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT posts, comments, dms
            FROM usage_counters
            WHERE user_id = %s AND platform = %s AND date = %s
        """, (user_id, platform, _today()))

        row = cur.fetchone()

    if not row:
        return {"posts": 0, "comments": 0, "dms": 0}

    return {
        "posts": row["posts"],
        "comments": row["comments"],
        "dms": row["dms"],
    }


def check_daily_limit(conn, user_id, platform, action):
    plan = require_active_subscription(conn, user_id)
    usage = get_today_usage(conn, user_id, platform)

    limits = {
        "post": plan["posts_per_day"],
        "comment": plan["comments_per_day"],
        "dm": plan["dms_per_day"],
    }

    if usage[action + "s"] >= limits[action]:
        raise PermissionError(
            f"Daily {action} limit reached ({usage[action + 's']}/{limits[action]})"
        )

def consume_daily_limit(conn, user_id, platform, action):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO usage_counters (user_id, platform, date)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (user_id, platform, _today()))

        cur.execute(f"""
            UPDATE usage_counters
            SET {action}s = {action}s + 1
            WHERE user_id = %s AND platform = %s AND date = %s
        """, (user_id, platform, _today()))

    conn.commit()

def check_and_consume_limit(conn, user_id, platform, action):
    """
    Legacy wrapper.
    SAFE:
    - Checks subscription
    - Checks limit
    - CONSUMES ONLY WHEN CALLED EXPLICITLY
    """
    check_daily_limit(conn, user_id, platform, action)
    consume_daily_limit(conn, user_id, platform, action)

def create_payment_intent(conn, user_id: int, plan_id: int, amount: int):
    payment_id = uuid.uuid4()

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO payment_intents (
                id, user_id, plan_id, amount, status
            )
            VALUES (%s, %s, %s, %s, 'pending')
            RETURNING id
        """, (str(payment_id), user_id, plan_id, amount))

    conn.commit()
    return payment_id

def attach_zeroid_reference(conn, payment_id, zeroid_reference: str):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE payment_intents
            SET zeroid_reference = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (zeroid_reference, str(payment_id)))

    conn.commit()


def log_payment_event(conn, payment_intent_id, event_type, payload):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO payment_events (
                payment_intent_id, event_type, payload
            )
            VALUES (%s, %s, %s)
        """, (payment_intent_id, event_type, json.dumps(payload)))

    conn.commit()

def mark_payment_paid(conn, zeroid_reference: str):
    """
    Idempotent payment confirmation.
    Will only update ONCE.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE payment_intents
            SET status = 'paid', updated_at = NOW()
            WHERE zeroid_reference = %s
              AND status != 'paid'
            RETURNING user_id, plan_id;
            """,
            (zeroid_reference,),
        )
        return cur.fetchone()


def activate_subscription_for_user(conn, user_id: int, plan_id: int):
    """
    Enforces SINGLE ACTIVE subscription.
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Deactivate existing subscriptions
        cur.execute(
            """
            UPDATE user_subscriptions
            SET is_active = FALSE
            WHERE user_id = %s;
            """,
            (user_id,),
        )

        # Get plan duration
        cur.execute(
            """
            SELECT duration_days
            FROM subscription_plans
            WHERE id = %s;
            """,
            (plan_id,),
        )
        plan = cur.fetchone()

        if not plan:
            raise ValueError("Invalid subscription plan")

        end_date = f"NOW() + INTERVAL '{plan['duration_days']} days'"

        # Activate new subscription
        cur.execute(
            f"""
            INSERT INTO user_subscriptions (
                user_id,
                plan_id,
                start_date,
                end_date,
                is_active
            )
            VALUES (%s, %s, NOW(), {end_date}, TRUE);
            """,
            (user_id, plan_id),
        )


# =====================
# Admin Operations
# ====================

# Admin Checker
def is_admin_user(user_id: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_admin FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    return bool(row and row["is_admin"])


# List All Users
def admin_list_users():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    u.id,
                    u.email,
                    u.is_active,
                    u.is_admin,
                    u.created_at,
                    us.start_date,
                    us.end_date,
                    us.is_active AS subscription_active,
                    sp.name AS plan_name
                FROM users u
                LEFT JOIN user_subscriptions us
                    ON us.user_id = u.id AND us.is_active = TRUE
                LEFT JOIN subscription_plans sp
                    ON sp.id = us.plan_id
                ORDER BY u.created_at DESC;
            """)
            return cur.fetchall()


# Activate or Deactivate User
def admin_set_user_active(user_id: int, is_active: bool):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET is_active = %s,
                    disabled_at = CASE
                        WHEN %s = FALSE THEN NOW()
                        ELSE NULL
                    END
                WHERE id = %s;
            """, (is_active, is_active, user_id))
        conn.commit()


# Extend User Subscription
def admin_extend_subscription(user_id: int, days: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE user_subscriptions
                SET end_date = end_date + (%s || ' days')::INTERVAL
                WHERE user_id = %s
                  AND is_active = TRUE;
            """, (f"{days} days", user_id))
        conn.commit()

# View User Payment History
def admin_get_user_payments(user_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    amount,
                    currency,
                    status,
                    created_at
                FROM payment_intents
                WHERE user_id = %s
                ORDER BY created_at DESC;
            """, (user_id,))
            return cur.fetchall()

from app.services.email import send_password_reset_email
import secrets
def create_password_reset_token(email: str) -> None:
    """
    Always succeeds silently.
    If user does not exist, nothing happens.
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE email = %s AND is_active = TRUE",
                (email,),
            )
            user = cur.fetchone()

            if not user:
                return  # silent exit (security)

            token = secrets.token_urlsafe(48)
            expires_at = datetime.utcnow() + timedelta(minutes=30)

            cur.execute(
                """
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (%s, %s, %s)
                """,
                (user["id"], token, expires_at),
            )

    # Hook email sending
    send_password_reset_email(email, token)

def reset_password_with_token(token: str, new_password: str) -> bool:
    from app.utils.security import hash_password

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT prt.id, prt.user_id
                FROM password_reset_tokens prt
                WHERE prt.token = %s
                  AND prt.used = FALSE
                  AND prt.expires_at > NOW()
                """,
                (token,),
            )
            row = cur.fetchone()

            if not row:
                return False

            password_hash = hash_password(new_password)

            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (password_hash, row["user_id"]),
            )

            cur.execute(
                "UPDATE password_reset_tokens SET used = TRUE WHERE id = %s",
                (row["id"],),
            )

    return True


def set_user_admin_status(user_id: int, is_admin: bool) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET is_admin = %s
                WHERE id = %s
                """,
                (is_admin, user_id),
            )
            return cur.rowcount > 0

def get_admin_count() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE is_admin = TRUE"
            )
            return cur.fetchone()[0]
