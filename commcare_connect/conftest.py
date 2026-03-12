import pytest
from rest_framework.test import APIClient, APIRequestFactory

from commcare_connect.organization.models import Organization
from commcare_connect.users.models import User
from commcare_connect.users.tests.factories import (
    MobileUserFactory,
    OrgWithUsersFactory,
    ProgramManagerOrgWithUsersFactory,
    UserFactory,
)


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """APIRequestFactory instance"""
    return APIRequestFactory()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def organization(db) -> Organization:
    return OrgWithUsersFactory()


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture
def mobile_user(db) -> User:
    return MobileUserFactory()


@pytest.fixture
def org_user_member(organization) -> User:
    return organization.memberships.filter(role="member").first().user


@pytest.fixture
def org_user_admin(organization) -> User:
    return organization.memberships.filter(role="admin").first().user


@pytest.fixture
def program_manager_org(db) -> Organization:
    return ProgramManagerOrgWithUsersFactory()


@pytest.fixture
def program_manager_org_user_member(program_manager_org) -> User:
    return program_manager_org.memberships.filter(role="member").first().user


@pytest.fixture
def program_manager_org_user_admin(program_manager_org) -> User:
    return program_manager_org.memberships.filter(role="admin").first().user
