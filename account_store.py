"""Local account and saved-state storage for Studiekompas."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager


PASSWORD_ITERATIONS = 310_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class AccountError(ValueError):
    """Raised when account data does not meet the account rules."""


def database_path() -> Path:
    configured_path = os.getenv("STUDIEKOMPAS_DB")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parent / "data" / "studiekompas.sqlite3"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_state (
                username TEXT PRIMARY KEY COLLATE NOCASE
                    REFERENCES accounts(username) ON DELETE CASCADE,
                state_json TEXT NOT NULL
            );
            """
        )
        with connection:
            yield connection
    finally:
        connection.close()


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )


def create_account(username: str, password: str) -> str:
    normalized_username = username.strip()
    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise AccountError(
            "Brugernavnet skal være 3–32 tegn og må kun indeholde engelske bogstaver, tal, punktum, bindestreg og understreg."
        )
    if len(password) < 8:
        raise AccountError("Adgangskoden skal være mindst 8 tegn.")
    if len(password) > 128:
        raise AccountError("Adgangskoden må højst være 128 tegn.")

    salt = secrets.token_bytes(16)
    password_hash = _password_hash(password, salt)
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO accounts (username, password_salt, password_hash)
                VALUES (?, ?, ?)
                """,
                (normalized_username, salt.hex(), password_hash.hex()),
            )
    except sqlite3.IntegrityError as error:
        raise AccountError("Brugernavnet er allerede taget.") from error
    return normalized_username


def authenticate_account(username: str, password: str) -> str | None:
    normalized_username = username.strip()
    with _connect() as connection:
        account = connection.execute(
            """
            SELECT username, password_salt, password_hash
            FROM accounts
            WHERE username = ? COLLATE NOCASE
            """,
            (normalized_username,),
        ).fetchone()
    if account is None:
        _password_hash(password, bytes(16))
        return None

    stored_hash = bytes.fromhex(account[2])
    supplied_hash = _password_hash(password, bytes.fromhex(account[1]))
    if not hmac.compare_digest(supplied_hash, stored_hash):
        return None
    return str(account[0])


def load_account_state(username: str) -> dict[str, object]:
    with _connect() as connection:
        result = connection.execute(
            "SELECT state_json FROM account_state WHERE username = ?",
            (username,),
        ).fetchone()
    if result is None:
        return {}

    state = json.loads(result[0])
    if not isinstance(state, dict):
        raise ValueError("De gemte kontodata har et ugyldigt format.")
    return state


def save_account_state(username: str, state_json: str) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO account_state (username, state_json)
            VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET state_json = excluded.state_json
            """,
            (username, state_json),
        )


def delete_account_state(username: str) -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM account_state WHERE username = ?", (username,))
