import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import AuthToken

from .helpers import USER_KEYS, error_code, get, post

PASSWORD = "bap-meokja-2026"


class PasswordAccountTests(TestCase):
    def sign_up(self, username="metchu_user", password=PASSWORD):
        return post(self.client, "/api/auth/signup/", {"username": username, "password": password})

    def test_sign_up_returns_a_token_that_signs_in(self):
        response = self.sign_up()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body["user"]), USER_KEYS)
        self.assertEqual(body["user"], {"username": "metchu_user", "google_email": None, "has_password": True})
        me = get(self.client, "/api/auth/me/", body["token"])
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json(), {"user": body["user"]})

    def test_log_in_takes_the_username_in_any_case(self):
        self.sign_up("Metchu_User")
        response = post(self.client, "/api/auth/login/", {"username": "metchu_user", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "Metchu_User")

    def test_username_is_unique_ignoring_case(self):
        self.sign_up("metchu_user")
        response = self.sign_up("METCHU_USER")
        self.assertEqual((response.status_code, error_code(response)), (409, "username_taken"))

    def test_korean_usernames_are_allowed(self):
        self.assertEqual(self.sign_up("멧츄사랑").status_code, 201)

    def test_bad_usernames_are_refused(self):
        for username in ("ab", "has space", "x" * 31, "semi;colon"):
            with self.subTest(username=username):
                response = self.sign_up(username)
                self.assertEqual((response.status_code, error_code(response)), (400, "invalid_username"))
        self.assertFalse(get_user_model().objects.exists())

    def test_weak_passwords_are_refused(self):
        for password in ("short1", "12345678", "password", "metchu_user1"):
            with self.subTest(password=password):
                response = self.sign_up(password=password)
                self.assertEqual((response.status_code, error_code(response)), (400, "weak_password"))
                self.assertTrue(response.json()["error"]["message"])
        self.assertFalse(get_user_model().objects.exists())

    def test_missing_fields_and_bad_json_are_400(self):
        for body in ({}, {"username": "metchu_user"}, {"password": PASSWORD}, {"username": 3, "password": PASSWORD}):
            with self.subTest(body=body):
                response = post(self.client, "/api/auth/signup/", body)
                self.assertEqual((response.status_code, error_code(response)), (400, "invalid_request"))
        response = self.client.post("/api/auth/login/", data="not json", content_type="application/json")
        self.assertEqual((response.status_code, error_code(response)), (400, "invalid_request"))

    def test_wrong_password_and_unknown_user_get_the_same_401(self):
        self.sign_up()
        wrong = post(self.client, "/api/auth/login/", {"username": "metchu_user", "password": "not-it-2026"})
        unknown = post(self.client, "/api/auth/login/", {"username": "nobody_here", "password": PASSWORD})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertEqual(error_code(wrong), "invalid_credentials")

    def test_only_a_hash_of_the_token_is_stored(self):
        token = self.sign_up().json()["token"]
        stored = AuthToken.objects.get()
        self.assertNotIn(token, stored.key_hash)
        self.assertEqual(stored.key_hash, hashlib.sha256(token.encode()).hexdigest())

    def test_log_out_ends_only_that_device(self):
        first = self.sign_up().json()["token"]
        second = post(self.client, "/api/auth/login/", {"username": "metchu_user", "password": PASSWORD}).json()["token"]
        self.assertEqual(post(self.client, "/api/auth/logout/", token=first).status_code, 204)
        self.assertEqual(get(self.client, "/api/auth/me/", first).status_code, 401)
        self.assertEqual(get(self.client, "/api/auth/me/", second).status_code, 200)

    def test_signed_in_endpoints_need_a_valid_token(self):
        for token in (None, "made-up-token"):
            with self.subTest(token=token):
                me = get(self.client, "/api/auth/me/", token)
                self.assertEqual((me.status_code, error_code(me)), (401, "not_authenticated"))
                out = post(self.client, "/api/auth/logout/", token=token)
                self.assertEqual((out.status_code, error_code(out)), (401, "not_authenticated"))
        token = self.sign_up().json()["token"]
        other_scheme = self.client.get("/api/auth/me/", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(other_scheme.status_code, 401)

    def test_a_disabled_user_cannot_sign_in(self):
        token = self.sign_up().json()["token"]
        get_user_model().objects.update(is_active=False)
        self.assertEqual(get(self.client, "/api/auth/me/", token).status_code, 401)
        response = post(self.client, "/api/auth/login/", {"username": "metchu_user", "password": PASSWORD})
        self.assertEqual(response.status_code, 401)

    def test_wrong_methods_are_405(self):
        self.assertEqual(self.client.get("/api/auth/signup/").status_code, 405)
        self.assertEqual(post(self.client, "/api/auth/me/").status_code, 405)
