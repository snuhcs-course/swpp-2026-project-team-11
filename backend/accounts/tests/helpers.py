"""Shared pieces for the accounts API tests."""
import json

USER_KEYS = {"username", "google_email", "has_password"}


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Token {token}"} if token else {}
    return client.post(path, data=json.dumps(body or {}), content_type="application/json", headers=headers)


def get(client, path, token=None):
    headers = {"Authorization": f"Token {token}"} if token else {}
    return client.get(path, headers=headers)


def error_code(response):
    return response.json()["error"]["code"]
