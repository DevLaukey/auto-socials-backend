"""
Script to create a test user in the database.
Run from the Backend directory with: python create_user.py
"""

from app.services.auth_database import add_user, get_user_by_email, set_user_admin_status
from app.utils.security import hash_password

def create_test_user(email: str, password: str, make_admin: bool = False):
    """Create a test user in the database."""

    # Check if user already exists
    existing = get_user_by_email(email)
    if existing:
        print(f"User '{email}' already exists with ID: {existing['id']}")
        if make_admin:
            set_user_admin_status(existing['id'], True)
            print(f"Ensured admin privileges for user ID: {existing['id']}")
        return existing['id']

    # Hash the password and create user
    password_hash = hash_password(password)
    user_id = add_user(email, password_hash)

    if user_id:
        print(f"Created user '{email}' with ID: {user_id}")

        if make_admin:
            set_user_admin_status(user_id, True)
            print(f"Granted admin privileges to user ID: {user_id}")

        return user_id
    else:
        print(f"Failed to create user '{email}' (may already exist)")
        return None

if __name__ == "__main__":
    # Create admin user
    print("Creating admin user...\n")

    create_test_user(
        email="admin@autosocials.com",
        password="Admin@2026!",
        make_admin=True
    )

    print("\n" + "="*50)
    print("ADMIN LOGIN CREDENTIALS")
    print("="*50)
    print("Email:    admin@autosocials.com")
    print("Password: Admin@2026!")
    print("="*50)
