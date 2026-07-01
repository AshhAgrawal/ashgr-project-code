from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError


SESSION_TTL = timedelta(days=7)
PASSWORD_SALT_BYTES = 16
PASSWORD_HASH_BYTES = 64
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
AUTHENTICATION_FEATURE = "authentication"


class AuthError(Exception):
    """A user-facing authentication error."""


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise AuthError("Enter a valid email address.")
    return normalized


def validate_name(name: str) -> str:
    normalized = " ".join(name.strip().split())
    if not 2 <= len(normalized) <= 80:
        raise AuthError("Name must be between 2 and 80 characters.")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise AuthError("Password must be at least 10 characters.")
    if len(password) > 256:
        raise AuthError("Password is too long.")


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    validate_password(password)
    salt = salt or secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=PASSWORD_HASH_BYTES,
    )
    return (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, salt_b64: str, digest_b64: str) -> bool:
    try:
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def public_user(user: dict[str, Any]) -> dict[str, str]:
    account_type = user.get("account_type", "member")
    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": "" if account_type == "guest" else user["email"],
        "role": user.get("role", "staff"),
        "account_type": account_type,
    }


class AuthService:
    def __init__(self, database: Database[Any]) -> None:
        self.database = database
        self.users = database.users
        self.sessions = database.auth_sessions
        self.users.create_index(
            [("email", ASCENDING)], unique=True, name="uq_users_email"
        )
        self.users.create_index(
            [("guest_key_hash", ASCENDING)],
            unique=True,
            sparse=True,
            name="uq_users_guest_key_hash",
        )
        self.sessions.create_index(
            [("token_hash", ASCENDING)],
            unique=True,
            name="uq_auth_sessions_token_hash",
        )
        self.sessions.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_auth_sessions_expires_at",
        )

    def create_user(
        self,
        name: str,
        email: str,
        password: str,
        role: str = "staff",
    ) -> dict[str, Any]:
        normalized_name = validate_name(name)
        normalized_email = normalize_email(email)
        if role not in {"admin", "staff"}:
            raise AuthError("Role must be admin or staff.")
        salt, digest = hash_password(password)
        now = datetime.now(timezone.utc)
        document = {
            "name": normalized_name,
            "email": normalized_email,
            "role": role,
            "account_type": "member",
            "password": {
                "algorithm": "scrypt",
                "salt": salt,
                "digest": digest,
                "n": SCRYPT_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
            },
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.users.insert_one(document)
        except DuplicateKeyError as exc:
            raise AuthError("An account with this email already exists.") from exc
        document["_id"] = result.inserted_id
        return document

    def get_or_create_guest(
        self, browser_key: str | None
    ) -> tuple[dict[str, Any], str]:
        now = datetime.now(timezone.utc)
        if browser_key:
            existing = self.users.find_one_and_update(
                {
                    "guest_key_hash": self._token_hash(browser_key),
                    "account_type": "guest",
                },
                {
                    "$set": {"last_seen_at": now, "updated_at": now},
                    "$inc": {"visit_count": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if existing is not None:
                return existing, browser_key

        browser_key = secrets.token_urlsafe(32)
        guest_code = secrets.token_hex(4).upper()
        document = {
            "name": f"Guest {guest_code}",
            "email": f"guest-{guest_code.casefold()}@guest.local",
            "role": "staff",
            "account_type": "guest",
            "guest_key_hash": self._token_hash(browser_key),
            "visit_count": 1,
            "first_seen_at": now,
            "last_seen_at": now,
            "created_at": now,
            "updated_at": now,
        }
        result = self.users.insert_one(document)
        document["_id"] = result.inserted_id
        return document, browser_key

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        try:
            normalized_email = normalize_email(email)
        except AuthError:
            normalized_email = "invalid@example.invalid"
        user = self.users.find_one({"email": normalized_email})
        if user is None:
            # Spend comparable work for unknown accounts to reduce timing leakage.
            dummy_password = (password + "0" * 10)[:256]
            hash_password(dummy_password)
            return None
        password_data = user.get("password", {})
        if password_data.get("algorithm") != "scrypt":
            return None
        if not verify_password(
            password,
            password_data.get("salt", ""),
            password_data.get("digest", ""),
        ):
            return None
        return user

    def create_session(self, user_id: Any) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        self.sessions.insert_one(
            {
                "token_hash": self._token_hash(token),
                "user_id": user_id,
                "created_at": now,
                "expires_at": now + SESSION_TTL,
            }
        )
        return token

    def user_for_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        now = datetime.now(timezone.utc)
        session = self.sessions.find_one(
            {
                "token_hash": self._token_hash(token),
                "expires_at": {"$gt": now},
            }
        )
        if session is None:
            return None
        return self.users.find_one({"_id": session["user_id"]})

    def delete_session(self, token: str | None) -> None:
        if token:
            self.sessions.delete_one({"token_hash": self._token_hash(token)})

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class FeatureService:
    def __init__(self, database: Database[Any]) -> None:
        self.features = database.features
        self.features.update_one(
            {"_id": AUTHENTICATION_FEATURE},
            {
                "$setOnInsert": {
                    "enabled": True,
                    "description": "Require signup and login for workspace access.",
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    def authentication_enabled(self) -> bool:
        feature = self.features.find_one({"_id": AUTHENTICATION_FEATURE})
        return True if feature is None else bool(feature.get("enabled", True))
