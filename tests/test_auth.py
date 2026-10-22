import unittest
from unittest.mock import Mock, patch

from azure.core.credentials import AccessToken

from lib.auth import Auth


class AuthTests(unittest.TestCase):
    def test_reuses_credential_for_multiple_scopes(self):
        with patch("lib.auth.DefaultAzureCredential") as credential_type:
            credential = credential_type.return_value
            credential.get_token.side_effect = [
                AccessToken("power-bi-token", 9999999999),
                AccessToken("fabric-token", 9999999999),
                AccessToken("power-bi-token", 9999999999),
            ]
            auth = Auth()
            tokens = [
                auth.get_access_token(scope) for scope in ("power-bi", "fabric", "power-bi")
            ]
        credential_type.assert_called_once()
        self.assertEqual(tokens, ["power-bi-token", "fabric-token", "power-bi-token"])
        self.assertEqual(
            [call.args for call in credential.get_token.call_args_list],
            [("power-bi",), ("fabric",), ("power-bi",)],
        )

    def test_headers_use_requested_scope_and_allow_sdk_refresh(self):
        with patch("lib.auth.DefaultAzureCredential") as credential_type:
            credential_type.return_value.get_token.side_effect = [
                AccessToken("power-bi-token", 9999999999),
                AccessToken("fabric-token", 9999999999),
                AccessToken("refreshed-power-bi-token", 9999999999),
            ]
            auth = Auth()
            for scope, expected in (
                ("power-bi", "power-bi-token"),
                ("fabric", "fabric-token"),
                ("power-bi", "refreshed-power-bi-token"),
            ):
                headers = auth.get_api_auth_headers(scope)
                self.assertEqual(headers["Authorization"].split()[-1], expected)
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(auth.token, expected)
        credential_type.assert_called_once()

    def test_direct_token_does_not_replace_last_header_token(self):
        with patch("lib.auth.DefaultAzureCredential") as credential_type:
            credential_type.return_value.get_token.side_effect = [
                AccessToken("power-bi-token", 9999999999),
                AccessToken("graph-token", 9999999999),
            ]
            auth = Auth()
            auth.get_api_auth_headers("power-bi")
            self.assertEqual(auth.get_access_token("graph"), "graph-token")
            self.assertEqual(auth.token, "power-bi-token")

    def test_authentication_errors_propagate(self):
        with patch("lib.auth.DefaultAzureCredential", return_value=Mock()) as credential_type:
            credential_type.return_value.get_token.side_effect = RuntimeError("Sign-in failed")
            with self.assertRaisesRegex(RuntimeError, "Sign-in failed"):
                Auth().get_api_auth_headers("fabric")


if __name__ == "__main__":
    unittest.main()
