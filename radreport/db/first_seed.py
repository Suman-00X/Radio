"""Seeds a brand-new database once: the model catalog, the first product admin, the demo logins and a demo lab.

Order: take a database-wide advisory lock, so API workers starting together seed once between them ->
check the tenant table, and stop if any lab exists -> run the seeders from devtools/seed.py in one
transaction (seed_if_empty) -> bring the demo logins in step with the settings whether or not it
seeded (sync_demo_logins), since a host without a shell has no other way to. The API calls both on
start; they also run on their own:

    python -m radreport.db.first_seed
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import text

from radreport.core.logging import configure_logging, get_logger
from radreport.db.session import system_session

log = get_logger(__name__)

#: Key of the advisory lock held while seeding; any constant shared by every process works.
SEED_LOCK_KEY = 0x5EED_0001


def seed_if_empty() -> bool:
    """Seed when the tenant table is empty; True when this call seeded."""
    from radreport.devtools.seed import ADMIN_PASSWORD_ENV, seed_demo_accounts, seed_demo_tenant, seed_model_catalog, seed_platform_admin

    with system_session() as session:
        # Held until this transaction ends: a second worker waits here, then sees the lab the first one created.
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEED_LOCK_KEY})
        if session.execute(text("SELECT EXISTS (SELECT 1 FROM tenant)")).scalar():
            return False

        password = os.environ.get(ADMIN_PASSWORD_ENV)
        seed_model_catalog(session)
        admin = seed_platform_admin(session, password=password)
        demo_logins = seed_demo_accounts(session)
        tenant_id = seed_demo_tenant(session, admin.id)

    log.info("first_seed_done", admin=admin.email, demo_logins=len(demo_logins), demo_tenant=str(tenant_id))
    if not password:
        log.warning("first_seed_admin_without_password", admin=admin.email, detail=f"set {ADMIN_PASSWORD_ENV} and run `make admin-password EMAIL={admin.email}`")
    return True


def sync_demo_logins() -> int:
    """Create or update every configured demo login, admin panel and lab; returns how many are in step."""
    from radreport.devtools.seed import seed_demo_accounts, seed_demo_lab_accounts

    with system_session() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEED_LOCK_KEY})
        platform = len(seed_demo_accounts(session))
    lab = len(seed_demo_lab_accounts())
    log.info("demo_logins_synced", admin_panel=platform, lab=lab)
    return platform + lab


def main() -> int:
    configure_logging()
    print("seeded" if seed_if_empty() else "skipped: the database already has a lab")
    print(f"demo logins in step: {sync_demo_logins()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
