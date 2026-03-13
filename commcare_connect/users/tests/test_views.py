import json
from unittest import mock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse

from commcare_connect.users.models import ConnectIDUserLink, User
from commcare_connect.users.views import UserToggleView, create_user_link_view

pytestmark = pytest.mark.django_db


class TestCreateUserLinkView:
    def test_view(self, mobile_user: User, rf: RequestFactory):
        request = rf.post("/fake-url/", data={"commcare_username": "abc", "connect_username": mobile_user.username})
        request.user = mobile_user
        with mock.patch(
            "oauth2_provider.views.mixins.ClientProtectedResourceMixin.authenticate_client"
        ) as authenticate_client:
            authenticate_client.return_value = True
            response = create_user_link_view(request)
        user_link = ConnectIDUserLink.objects.get(user=mobile_user)
        assert response.status_code == 201
        assert user_link.commcare_username == "abc"


class TestRetrieveUserOTPView:
    @property
    def url(self):
        return reverse("users:connect_user_otp")

    def test_non_superuser_cannot_access_page(self, user, client):
        assert not user.is_superuser

        client.force_login(user)
        response = client.get(self.url)

        assert response.status_code == 403

    @patch("commcare_connect.users.views.get_user_otp")
    def test_can_get_user_otp(self, get_user_otp_mock, user, client):
        get_user_otp_mock.return_value = "1234"
        response = self._get_response(client, user)

        messages = list(response.context["messages"])
        assert str(messages[0]) == "The user's OTP is: 1234"

    @patch("commcare_connect.users.views.get_user_otp")
    def test_no_otp_returned(self, get_user_otp_mock, user, client):
        get_user_otp_mock.return_value = None
        response = self._get_response(client, user)

        expected_failure_message = (
            "Failed to fetch OTP. Please make sure the number is correct "
            "and that the user has started their device seating process."
        )

        messages = list(response.context["messages"])
        assert str(messages[0]) == expected_failure_message

    def _get_response(self, client, user):
        perm = Permission.objects.get(codename="otp_access")
        user.user_permissions.add(perm)

        client.force_login(user)
        return client.post(self.url, data={"phone_number": "+1234567890"}, follow=True)


class TestUserToggleView:
    def test_no_toggles(self, mobile_user: User, rf: RequestFactory):
        user_toggle_view = UserToggleView.as_view()
        request = rf.get("/fake-url/", data={"username": mobile_user.username})
        request.user = mobile_user
        with mock.patch(
            "oauth2_provider.views.mixins.ClientProtectedResourceMixin.authenticate_client"
        ) as authenticate_client:
            authenticate_client.return_value = True
            response = user_toggle_view(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert "toggles" in data
        assert data["toggles"] == []

    def test_toggles_returns_empty(self, mobile_user: User, rf: RequestFactory):
        # waffle was removed from INSTALLED_APPS during labs simplification;
        # UserToggleView now always returns empty toggles.
        user_toggle_view = UserToggleView.as_view()
        request = rf.get("/fake-url/", data={"username": mobile_user.username})
        request.user = mobile_user
        with mock.patch(
            "oauth2_provider.views.mixins.ClientProtectedResourceMixin.authenticate_client"
        ) as authenticate_client:
            authenticate_client.return_value = True
            response = user_toggle_view(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert "toggles" in data
        assert data["toggles"] == []
