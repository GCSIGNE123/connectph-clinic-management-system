"""One-off bootstrap script: seed the first Platform Administrator account.

There is no self-registration for platform admins (by design - see
docs/ARCHITECTURE.md). Run once against the real dev DB:

    python scripts_seed_platform_admin.py
"""
import asyncio

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.platform_admin_user import PlatformAdminRole, PlatformAdminUser
from app.repositories.platform_admin_repository import PlatformAdminUserRepository


async def main() -> None:
    async with AsyncSessionLocal() as session:
        repo = PlatformAdminUserRepository(session)
        existing = await repo.get_by_email("platformadmin@connectph.dev")
        if existing:
            print("Already exists:", existing.id)
            return
        admin = PlatformAdminUser(
            email="platformadmin@connectph.dev",
            username="platformadmin",
            hashed_password=hash_password("PlatformAdmin123!"),
            full_name="CONNECT.PH Platform Administrator",
            role=PlatformAdminRole.PLATFORM_ADMINISTRATOR,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print("Created platform admin:", admin.id)


if __name__ == "__main__":
    asyncio.run(main())
