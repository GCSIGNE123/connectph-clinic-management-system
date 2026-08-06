"""Shared pytest fixtures: test database setup, seeded roles, and an ASGI test client.

Requires a reachable Postgres instance at `settings.DATABASE_URL` (asyncpg driver) -
the models use Postgres-specific types (UUID, JSONB, gen_random_uuid()) so SQLite
is not a viable substitute. Point `DATABASE_URL` (env var / .env) at a disposable
test database before running these tests, e.g.:

    DATABASE_URL=postgresql+asyncpg://clinic_user:clinic_password@localhost:5432/connectph_clinic_test
"""

import asyncio
import sys
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

if sys.platform == "win32":
    # asyncpg's Proactor-based transport handling occasionally hands a future
    # tied to a since-closed event loop across pytest-asyncio's per-test event
    # loops (`asyncio.set_event_loop_policy`/teardown churn). The selector
    # event loop policy avoids the Proactor-specific IOCP handle reuse issue.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models.role import Role
from app.models.seed import PERMISSION_SEED_DATA, ROLE_PERMISSION_SEED_DATA, ROLE_SEED_DATA

# Import all models so Base.metadata is fully populated. Aliased (rather than
# `import app.models`) so this doesn't rebind the module-level `app` name
# above (the FastAPI instance from `app.main`) to the `app` package.
from app import models as _app_models  # noqa: F401
from app.core.config import settings


@pytest_asyncio.fixture(scope="session")
async def engine():
    # Safety guard: this fixture drops and recreates the ENTIRE public schema
    # of whatever `DATABASE_URL` points to. That destroyed the seeded dev
    # Owner login/demo clinic once when a test run was accidentally pointed
    # at the dev database - refuse to run unless the DB name looks like a
    # disposable test database (see the module docstring above).
    if "test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower():
        raise RuntimeError(
            "Refusing to run tests: DATABASE_URL does not point at a database "
            "whose name contains 'test'. This fixture drops the entire public "
            "schema - point DATABASE_URL at a disposable test database, e.g. "
            "connectph_clinic_test, before running pytest."
        )
    test_engine = create_async_engine(settings.DATABASE_URL, future=True)
    async with test_engine.begin() as conn:
        # `Base.metadata.drop_all` cannot topologically sort DROP order once
        # there's a genuine FK cycle across tables (e.g. branches.manager_id
        # -> users, users.branch_id -> branches) without every FK in the
        # cycle being explicitly named for ALTER-based dropping. Resetting
        # the whole schema sidesteps dependency ordering entirely and is
        # safe here since this only ever targets a disposable test database.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    async with session_maker() as seed_session:
        await _seed_roles_and_permissions(seed_session)
        await seed_session.commit()

    yield test_engine

    await test_engine.dispose()


async def _seed_roles_and_permissions(session: AsyncSession) -> None:
    from app.models.permission import Permission
    from app.models.role_permission import RolePermission

    role_ids: dict[str, uuid.UUID] = {}
    for role in ROLE_SEED_DATA:
        instance = Role(name=role["name"], description=role["description"])
        session.add(instance)
        await session.flush()
        role_ids[role["name"]] = instance.id

    permission_ids: dict[str, uuid.UUID] = {}
    for permission in PERMISSION_SEED_DATA:
        instance = Permission(code=permission["code"], description=permission["description"])
        session.add(instance)
        await session.flush()
        permission_ids[permission["code"]] = instance.id

    for role_name, codes in ROLE_PERMISSION_SEED_DATA.items():
        for code in codes:
            session.add(RolePermission(role_id=role_ids[role_name], permission_id=permission_ids[code]))
    await session.flush()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def owner_role(db_session: AsyncSession) -> Role:
    result = await db_session.execute(select(Role).where(Role.name == "Owner"))
    return result.scalar_one()


def unique_slug(prefix: str = "clinic") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest_asyncio.fixture
async def make_clinic_with_owner(db_session: AsyncSession, owner_role: Role):
    """Factory fixture: creates a clinic + an Owner user with a known password.

    Returns an async callable `(email=None, username=None, password="...") -> (clinic, user, password)`.
    """
    from app.core.security import hash_password
    from app.models.clinic import Clinic
    from app.models.user import User

    async def _make(
        *,
        password: str = "SuperSecret123!",
        email: str | None = None,
        username: str | None = None,
    ):
        suffix = uuid.uuid4().hex[:8]
        clinic = Clinic(name=f"Test Clinic {suffix}", slug=unique_slug())
        db_session.add(clinic)
        await db_session.flush()

        user = User(
            clinic_id=clinic.id,
            email=email or f"owner-{suffix}@example.com",
            username=username or f"owner{suffix}",
            hashed_password=hash_password(password),
            first_name="Test",
            last_name="Owner",
            role_id=owner_role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return clinic, user, password

    return _make
