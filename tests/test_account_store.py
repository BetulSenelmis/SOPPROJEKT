import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from account_store import (
    AccountError,
    authenticate_account,
    create_account,
    delete_account_state,
    load_account_state,
    save_account_state,
)


class AccountStoreTests(unittest.TestCase):
    def test_accounts_hash_passwords_and_persist_separate_state(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "accounts.sqlite3")
            with patch.dict(os.environ, {"STUDIEKOMPAS_DB": database}):
                username = create_account("student_1", "secure-password")
                self.assertEqual(authenticate_account("STUDENT_1", "secure-password"), username)
                self.assertIsNone(authenticate_account(username, "wrong-password"))

                save_account_state(username, '{"profile": {"klassetrin": "2.g"}}')
                self.assertEqual(
                    load_account_state(username),
                    {"profile": {"klassetrin": "2.g"}},
                )
                self.assertEqual(load_account_state("missing_user"), {})

                with closing(sqlite3.connect(database)) as connection:
                    stored_password = connection.execute(
                        "SELECT password_hash FROM accounts WHERE username = ?",
                        (username,),
                    ).fetchone()[0]
                self.assertNotEqual(stored_password, "secure-password")

                delete_account_state(username)
                self.assertEqual(load_account_state(username), {})

    def test_account_creation_validates_username_password_and_uniqueness(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"STUDIEKOMPAS_DB": os.path.join(directory, "accounts.sqlite3")},
            ):
                with self.assertRaises(AccountError):
                    create_account("ab", "secure-password")
                with self.assertRaises(AccountError):
                    create_account("student_1", "short")
                create_account("student_1", "secure-password")
                with self.assertRaises(AccountError):
                    create_account("STUDENT_1", "different-password")


if __name__ == "__main__":
    unittest.main()
