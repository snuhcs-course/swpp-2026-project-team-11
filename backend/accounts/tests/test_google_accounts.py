from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from google.auth.exceptions import TransportError

from accounts.models import GoogleIdentity

from .helpers import error_code, get, post

CLIENT_ID = "web-client.apps.googleusercontent.com"
# What google-auth returns for each made-up ID token after checking it.
CLAIMS = {
    "token-minji": {"sub": "1001", "email": "minji@example.com", "email_verified": True},
    "token-unverified": {"sub": "1002", "email": "someone@example.com", "email_verified": False},
    "token-other": {"sub": "1003", "email": "minji@example.org", "email_verified": True},
    "token-no-sub": {"email": "x@example.com", "email_verified": True},
}


@override_settings(GOOGLE_OAUTH_CLIENT_ID=CLIENT_ID)
class GoogleAccountTests(TestCase):
    def setUp(self):
        patcher = mock.patch("accounts.google.id_token.verify_oauth2_token", side_effect=self.verify)
        self.verify_token = patcher.start()
        self.addCleanup(patcher.stop)

    def verify(self, token, request, audience):
        self.assertEqual(audience, CLIENT_ID)
        if token not in CLAIMS:
            raise ValueError("Could not verify token signature.")
        return dict(CLAIMS[token])

    def google(self, id_token="token-minji"):
        return post(self.client, "/api/auth/google/", {"id_token": id_token})

    def sign_up(self, username="metchu_user"):
        body = {"username": username, "password": "bap-meokja-2026"}
        return post(self.client, "/api/auth/signup/", body).json()["token"]

    def test_first_google_sign_in_creates_an_account_without_password(self):
        response = self.google()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["created"])
        self.assertEqual(body["user"], {"username": "minji", "google_email": "minji@example.com",
                                        "has_password": False})
        self.assertEqual(get(self.client, "/api/auth/me/", body["token"]).json()["user"], body["user"])

    def test_signing_in_again_reaches_the_same_account(self):
        first = self.google().json()
        again = self.google()
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["created"])
        self.assertEqual(again.json()["user"], first["user"])
        self.assertNotEqual(again.json()["token"], first["token"])
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_a_taken_name_gets_a_number(self):
        self.sign_up("Minji")
        self.assertEqual(self.google().json()["user"]["username"], "minji2")

    def test_an_unverified_email_is_not_kept(self):
        user = self.google("token-unverified").json()["user"]
        self.assertEqual((user["username"], user["google_email"]), ("google", ""))

    def test_bad_tokens_are_401_and_missing_ones_400(self):
        for token in ("forged", "token-no-sub"):
            with self.subTest(token=token):
                response = self.google(token)
                self.assertEqual((response.status_code, error_code(response)), (401, "invalid_google_token"))
        response = post(self.client, "/api/auth/google/", {})
        self.assertEqual((response.status_code, error_code(response)), (400, "invalid_request"))
        self.assertFalse(get_user_model().objects.exists())

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_without_a_client_id_google_is_unavailable(self):
        response = self.google()
        self.assertEqual((response.status_code, error_code(response)), (503, "google_unavailable"))
        self.verify_token.assert_not_called()

    def test_google_unreachable_is_503(self):
        self.verify_token.side_effect = TransportError("connection refused")
        response = self.google()
        self.assertEqual((response.status_code, error_code(response)), (503, "google_unavailable"))

    def test_linking_lets_either_way_reach_the_password_account(self):
        token = self.sign_up()
        linked = post(self.client, "/api/auth/google/link/", {"id_token": "token-minji"}, token)
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json()["user"], {"username": "metchu_user", "google_email": "minji@example.com",
                                                 "has_password": True})
        via_google = self.google()
        self.assertEqual(via_google.status_code, 200)
        self.assertEqual(via_google.json()["user"]["username"], "metchu_user")
        again = post(self.client, "/api/auth/google/link/", {"id_token": "token-minji"}, token)
        self.assertEqual(again.status_code, 200)

    def test_linking_needs_a_signed_in_user(self):
        response = post(self.client, "/api/auth/google/link/", {"id_token": "token-minji"})
        self.assertEqual((response.status_code, error_code(response)), (401, "not_authenticated"))
        self.verify_token.assert_not_called()

    def test_a_google_account_belongs_to_one_user(self):
        self.google()  # creates the user "minji"
        token = self.sign_up()
        response = post(self.client, "/api/auth/google/link/", {"id_token": "token-minji"}, token)
        self.assertEqual((response.status_code, error_code(response)), (409, "google_in_use"))

    def test_a_user_links_one_google_account(self):
        token = self.sign_up()
        post(self.client, "/api/auth/google/link/", {"id_token": "token-minji"}, token)
        response = post(self.client, "/api/auth/google/link/", {"id_token": "token-other"}, token)
        self.assertEqual((response.status_code, error_code(response)), (409, "already_linked"))
        self.assertEqual(GoogleIdentity.objects.get().subject, "1001")
