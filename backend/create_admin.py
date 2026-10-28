"""
One-time script: create an admin user and a default workspace.
Run from the backend/ directory:
    python create_admin.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from core.database import AsyncSessionLocal, init_db, User, Workspace, AuditLog
from core.security import get_password_hash

import os

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@enterprise.local")
ADMIN_FULLNAME = os.environ.get("ADMIN_FULLNAME", "Administrator")

if not ADMIN_PASSWORD:
    print("[ERROR] Please set ADMIN_PASSWORD environment variable before running this script.")
    sys.exit(1)


async def main():
    print("Initialising database …")
    await init_db()

    async with AsyncSessionLocal() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.username == ADMIN_USERNAME))
        existing = result.scalars().first()

        if existing:
            print(f"[INFO] Admin user '{ADMIN_USERNAME}' already exists (id={existing.id}).")
            print(f"       Resetting password to: [REDACTED]")
            existing.hashed_password = get_password_hash(ADMIN_PASSWORD)
            existing.role = "admin"
            existing.is_active = True
            await db.commit()
            print("[OK] Password reset done.")
            return

        # Create admin user
        admin = User(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            full_name=ADMIN_FULLNAME,
            hashed_password=get_password_hash(ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        # Create default workspace for admin
        ws = Workspace(
            name="Admin Workspace",
            workspace_type="business",
            description="Default workspace for admin",
            owner_id=admin.id,
        )
        db.add(ws)
        db.add(AuditLog(user_id=admin.id, action="admin_seeded", resource="user"))
        await db.commit()

        print("=" * 50)
        print("  Admin user created successfully!")
        print(f"  Username : {ADMIN_USERNAME}")
        print(f"  Password : [REDACTED]")
        print(f"  Role     : admin")
        print(f"  User ID  : {admin.id}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
