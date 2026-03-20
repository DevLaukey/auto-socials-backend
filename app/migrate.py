"""
Database migration script for Fly.io release command.
Runs before the web server starts.
"""

import sys
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY = 3


def run_sql_migrations():
    """Execute migrations.sql against the database."""
    import os
    import psycopg2

    sql_path = os.path.join(os.path.dirname(__file__), "..", "migrations.sql")
    sql_path = os.path.abspath(sql_path)

    if not os.path.exists(sql_path):
        logger.warning(f"migrations.sql not found at {sql_path}, skipping.")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set, skipping migrations.sql")
        return

    logger.info(f"Running migrations.sql from {sql_path}...")
    with open(sql_path, "r") as f:
        sql = f.read()

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("migrations.sql executed successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations():
    """Run database migrations with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Migration attempt {attempt}/{MAX_RETRIES}")

            # Import here to catch connection errors
            from app.services.database import init_db
            from app.services.auth_database import init_auth_db, add_user, get_user_by_email, set_user_admin_status
            from app.utils.security import hash_password

            # Auth schema MUST be created first because app schema
            # tables may reference auth.users via foreign keys.
            logger.info("Initializing auth database...")
            init_auth_db()
            logger.info("Auth database initialized.")

            logger.info("Initializing main database...")
            init_db()
            logger.info("Main database initialized.")

            logger.info("Running SQL migrations...")
            run_sql_migrations()

            # Create default admin user
            logger.info("Creating default admin user...")
            admin_email = "admin@autosocials.com"
            admin_password = "Admin@2026!"

            existing = get_user_by_email(admin_email)
            if existing:
                set_user_admin_status(existing["id"], True)
                logger.info(f"Admin user already exists (ID: {existing['id']})")
            else:
                user_id = add_user(admin_email, hash_password(admin_password))
                if user_id:
                    set_user_admin_status(user_id, True)
                    logger.info(f"Created admin user (ID: {user_id})")

            logger.info("All migrations completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Migration attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("All migration attempts failed!")
                return False

    return False


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
