"""The demo logins shown on the sign-in pages work on a database that already has labs, keep one read-only role, and survive a restart."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from radreport.api.app import create_app
from radreport.core.config import get_settings
from radreport.core.types import UserRole
from radreport.db.first_seed import sync_demo_logins
from radreport.db.models.identity import AppUser
from radreport.db.models.tenancy import PlatformUser, Tenant
from radreport.db.session import system_session, tenant_session

pytestmark = pytest.mark.db


@pytest.fixture
def demo(migrated_db: str, two_tenants, monkeypatch: pytest.MonkeyPatch):
    tenant_id, _other = two_tenants
    with system_session(migrated_db) as session:
        slug = session.get(Tenant, tenant_id).slug
    tag = uuid.uuid4().hex[:8]
    accounts = [{"label": "Admin demo", "email": f"support-{tag}@demo.local", "password": "admin-demo-password", "role": "support"}, {"label": "Lab demo", "email": f"auditor-{tag}@demo.local", "password": "lab-demo-password", "role": "auditor", "lab": slug}, {"label": "No such lab", "email": f"ghost-{tag}@demo.local", "password": "ghost-demo-password", "role": "auditor", "lab": f"missing-{tag}"}]
    monkeypatch.setenv("RADREPORT_DEMO_ACCOUNTS", json.dumps(accounts))
    get_settings.cache_clear()
    yield {"db": migrated_db, "tenant_id": tenant_id, "slug": slug, "admin": accounts[0], "lab": accounts[1]}
    get_settings.cache_clear()


def _signs_in(demo: dict) -> tuple[int, int]:
    client = TestClient(create_app(), follow_redirects=False)
    admin = client.post("/admin/login", data={"email": demo["admin"]["email"], "password": demo["admin"]["password"]})
    lab = client.post("/auth/login", json={"lab": demo["slug"], "email": demo["lab"]["email"], "password": demo["lab"]["password"]})
    return admin.status_code, lab.status_code


def test_demo_logins_are_created_in_a_database_that_already_has_labs(demo: dict) -> None:
    assert _signs_in(demo) == (303, 401)
    # The lab with no such slug is skipped, not an error.
    assert sync_demo_logins() == 2
    admin_status, lab_status = _signs_in(demo)
    assert admin_status == 303 and lab_status == 200


def test_a_changed_password_is_synced_and_an_unchanged_one_is_left_alone(demo: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    sync_demo_logins()
    with system_session(demo["db"]) as session:
        first = session.query(PlatformUser.password_hash).filter_by(email=demo["admin"]["email"]).scalar()
    sync_demo_logins()
    with system_session(demo["db"]) as session:
        assert session.query(PlatformUser.password_hash).filter_by(email=demo["admin"]["email"]).scalar() == first, "a restart must not reset the password"

    demo["lab"]["password"] = "a-new-lab-demo-password"
    monkeypatch.setenv("RADREPORT_DEMO_ACCOUNTS", json.dumps([demo["admin"], demo["lab"]]))
    get_settings.cache_clear()
    sync_demo_logins()
    assert _signs_in(demo)[1] == 200


def test_a_lab_demo_login_keeps_only_its_read_only_role(demo: dict) -> None:
    with tenant_session(demo["tenant_id"], url=demo["db"]) as session:
        session.add(AppUser(tenant_id=demo["tenant_id"], employee_code=f"X-{uuid.uuid4().hex[:6]}", display_name="Was a radiologist", email=demo["lab"]["email"], roles=[UserRole.RADIOLOGIST, UserRole.AUDITOR]))
    sync_demo_logins()
    with tenant_session(demo["tenant_id"], url=demo["db"]) as session:
        roles = session.query(AppUser.roles).filter_by(tenant_id=demo["tenant_id"], email=demo["lab"]["email"]).scalar()
    assert roles == [UserRole.AUDITOR]
