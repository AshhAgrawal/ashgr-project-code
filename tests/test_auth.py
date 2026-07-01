from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from retail_agent.auth import (
    AuthError,
    AuthService,
    FeatureService,
    hash_password,
    normalize_email,
    public_user,
    validate_name,
    validate_password,
    verify_password,
)


class PasswordTests(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        salt, digest = hash_password("correct horse battery staple")
        self.assertTrue(
            verify_password("correct horse battery staple", salt, digest)
        )
        self.assertFalse(verify_password("incorrect password", salt, digest))

    def test_password_hashes_use_unique_salts(self) -> None:
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")
        self.assertNotEqual(first, second)

    def test_short_password_is_rejected(self) -> None:
        with self.assertRaisesRegex(AuthError, "at least 10"):
            validate_password("short")


class IdentityValidationTests(unittest.TestCase):
    def test_email_is_normalized(self) -> None:
        self.assertEqual(normalize_email("  TEAM@Example.COM "), "team@example.com")

    def test_invalid_email_is_rejected(self) -> None:
        with self.assertRaisesRegex(AuthError, "valid email"):
            normalize_email("not-an-email")

    def test_name_whitespace_is_normalized(self) -> None:
        self.assertEqual(validate_name("  Alex   Morgan "), "Alex Morgan")


class AuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = MagicMock()
        self.database.users = MagicMock()
        self.database.auth_sessions = MagicMock()
        self.service = AuthService(self.database)

    def test_create_authenticate_and_resolve_session(self) -> None:
        self.database.users.insert_one.return_value = SimpleNamespace(
            inserted_id="user-1"
        )
        user = self.service.create_user(
            "Alex Morgan", "ALEX@example.com", "a secure password"
        )
        self.assertEqual(user["email"], "alex@example.com")
        self.assertEqual(user["role"], "staff")
        self.assertNotIn("a secure password", str(user["password"]))

        self.database.users.find_one.return_value = user
        authenticated = self.service.authenticate(
            "alex@example.com", "a secure password"
        )
        self.assertEqual(authenticated, user)

        token = self.service.create_session(user["_id"])
        session = self.database.auth_sessions.insert_one.call_args.args[0]
        self.assertNotEqual(session["token_hash"], token)
        self.database.auth_sessions.find_one.return_value = session
        self.database.users.find_one.return_value = user
        self.assertEqual(self.service.user_for_session(token), user)

    def test_admin_role_can_only_be_assigned_explicitly(self) -> None:
        self.database.users.insert_one.return_value = SimpleNamespace(
            inserted_id="admin-1"
        )
        user = self.service.create_user(
            "Store Admin",
            "admin@example.com",
            "a secure password",
            role="admin",
        )
        self.assertEqual(user["role"], "admin")

        with self.assertRaisesRegex(AuthError, "admin or staff"):
            self.service.create_user(
                "Bad Role",
                "bad@example.com",
                "a secure password",
                role="owner",
            )

    def test_guest_uses_hashed_browser_key_and_staff_role(self) -> None:
        self.database.users.find_one_and_update.return_value = None
        self.database.users.insert_one.return_value = SimpleNamespace(
            inserted_id="guest-1"
        )
        guest, browser_key = self.service.get_or_create_guest(None)
        self.assertEqual(guest["role"], "staff")
        self.assertEqual(guest["account_type"], "guest")
        self.assertNotEqual(guest["guest_key_hash"], browser_key)
        self.assertEqual(guest["visit_count"], 1)
        self.assertEqual(public_user(guest)["email"], "")

        self.database.users.find_one_and_update.return_value = guest
        reused, reused_key = self.service.get_or_create_guest(browser_key)
        self.assertEqual(reused, guest)
        self.assertEqual(reused_key, browser_key)


class FeatureServiceTests(unittest.TestCase):
    def test_authentication_flag_is_read_from_database(self) -> None:
        database = MagicMock()
        database.features.find_one.return_value = {"enabled": False}
        service = FeatureService(database)
        self.assertFalse(service.authentication_enabled())
        database.features.update_one.assert_called_once()


if __name__ == "__main__":
    unittest.main()
