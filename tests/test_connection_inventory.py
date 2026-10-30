import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


SCRIPT = Path(__file__).resolve().parents[1] / "fabric-connection-inventory.py"
SPEC = importlib.util.spec_from_file_location("connection_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def response(payload, status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


class ConnectionInventoryTests(unittest.TestCase):
    def test_interactive_authentication(self):
        with patch.object(inventory, "Auth") as auth:
            self.assertIs(inventory.create_auth(), auth.return_value)
        auth.assert_called_once_with()

    def test_service_principal_authentication(self):
        with (
            patch.object(inventory, "TENANT_ID", "tenant"),
            patch.object(inventory, "CLIENT_ID", "client"),
            patch.object(inventory, "CLIENT_SECRET", "secret"),
            patch.object(inventory, "Auth") as auth,
        ):
            self.assertIs(inventory.create_auth(), auth.return_value)
        auth.assert_called_once_with(
            tenant_id="tenant", client_id="client", client_secret="secret"
        )

    def test_partial_credentials_are_rejected(self):
        with (
            patch.object(inventory, "TENANT_ID", "tenant"),
            patch.object(inventory, "Auth") as auth,
            self.assertRaisesRegex(ValueError, "Set TENANT_ID"),
        ):
            inventory.create_auth()
        auth.assert_not_called()

    def test_pagination_keeps_admin_endpoint(self):
        auth = Mock()
        session = Mock()
        token = "next+/=%3D"
        session.get.side_effect = [
            response({
                "value": [{"id": "first"}],
                "continuationToken": token,
                "continuationUri": "https://api.fabric.microsoft.com/v1/connections",
            }),
            response({"value": [{"id": "second"}]}),
        ]
        self.assertEqual(
            list(inventory.get_connections(auth, session)),
            [{"id": "first"}, {"id": "second"}],
        )
        self.assertEqual(session.get.call_count, 2)
        for call in session.get.call_args_list:
            self.assertEqual(call.args, (inventory.CONNECTIONS_URL,))
            self.assertEqual(call.kwargs["timeout"], inventory.REQUEST_TIMEOUT_SECONDS)
            self.assertEqual(
                call.kwargs["headers"], auth.get_api_auth_headers.return_value
            )
        self.assertEqual(session.get.call_args_list[0].kwargs["params"], {})
        self.assertEqual(
            session.get.call_args_list[1].kwargs["params"],
            {"continuationToken": token},
        )
        self.assertEqual(auth.get_api_auth_headers.call_count, 2)
        auth.get_api_auth_headers.assert_called_with(inventory.FABRIC_SCOPE)

    def test_throttling_retries_then_succeeds(self):
        session = Mock()
        session.get.side_effect = [
            response({}, status=429, headers={"Retry-After": "2"}),
            response({"value": []}),
        ]
        with patch.object(inventory.time, "sleep") as sleep:
            self.assertEqual(list(inventory.get_connections(Mock(), session)), [])
        sleep.assert_called_once_with(2)

    def test_http_errors_and_exhausted_retries_are_reported(self):
        for status in (401, 403, 429, 500):
            with (
                self.subTest(status=status),
                patch.object(inventory, "MAX_RETRIES", 1),
                patch.object(inventory.time, "sleep"),
            ):
                session = Mock()
                session.get.return_value = response({}, status=status)
                with self.assertRaises(requests.HTTPError):
                    list(inventory.get_connections(Mock(), session))
                self.assertEqual(session.get.call_count, 2 if status == 429 else 1)

    def test_flattening_includes_all_fields_and_preserves_false(self):
        connection = {
            "id": "connection",
            "displayName": "Sales, Europe",
            "allowConnectionUsageInGateway": False,
            "allowUsageInUserControlledCode": True,
            "connectionDetails": {"type": "SQL", "path": "server;database"},
            "credentialDetails": {"credentialType": "Basic", "skipTestConnection": False},
            "connectionRecency": {"createdDateTime": "2026-10-30T12:00:00Z"},
        }
        row = inventory.flatten_connection(connection)
        self.assertEqual(list(row), inventory.CSV_FIELDS)
        self.assertEqual(row["connectionDetails.path"], "server;database")
        self.assertEqual(row["credentialDetails.credentialType"], "Basic")
        self.assertIs(row["credentialDetails.skipTestConnection"], False)
        self.assertIs(row["allowConnectionUsageInGateway"], False)
        self.assertIs(row["allowUsageInUserControlledCode"], True)
        self.assertEqual(row["connectionRecency.createdDateTime"], "2026-10-30T12:00:00Z")
        self.assertEqual(row["connectionRecency.lastBoundDateTime"], "")
        self.assertEqual(row["myRole"], "")
        self.assertEqual(
            inventory.flatten_connection({"connectionRecency": None})[
                "connectionRecency.createdDateTime"
            ],
            "",
        )

    def test_csv_export_and_empty_inventory(self):
        for connections in ([{"id": "one", "displayName": "Sales, Europe\nTeam"}], []):
            with (
                self.subTest(connections=connections),
                tempfile.TemporaryDirectory() as directory,
                patch.object(inventory, "OUTPUT_FILE", Path(directory) / "output" / "connections.csv"),
                patch.object(inventory, "create_auth"),
                patch.object(inventory, "get_connections", return_value=iter(connections)),
            ):
                inventory.main()
                with inventory.OUTPUT_FILE.open(newline="", encoding="utf-8-sig") as output:
                    reader = csv.DictReader(output)
                    rows = list(reader)
                self.assertEqual(reader.fieldnames, inventory.CSV_FIELDS)
                self.assertEqual(len(rows), len(connections))
                if connections:
                    self.assertEqual(rows[0]["displayName"], connections[0]["displayName"])

    def test_failed_later_page_does_not_replace_existing_csv(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(inventory, "OUTPUT_FILE", Path(directory) / "connections.csv"),
            patch.object(inventory, "create_auth"),
            patch.object(inventory.requests, "Session") as session_type,
        ):
            inventory.OUTPUT_FILE.write_text("existing inventory", encoding="utf-8")
            session = session_type.return_value.__enter__.return_value
            session.get.side_effect = [
                response({"value": [{"id": "one"}], "continuationToken": "next"}),
                response({}, status=403),
            ]
            with self.assertRaises(requests.HTTPError):
                inventory.main()
            self.assertEqual(
                inventory.OUTPUT_FILE.read_text(encoding="utf-8"), "existing inventory"
            )


if __name__ == "__main__":
    unittest.main()
