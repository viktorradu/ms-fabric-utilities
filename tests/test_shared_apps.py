import base64
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


SCRIPT = Path(__file__).resolve().parents[1] / "powerbi-get-organizations-shared-apps.py"
SPEC = importlib.util.spec_from_file_location("shared_apps", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
shared_apps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shared_apps)


def response(payload, status=200, headers=None):
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


def definition_response(parent_app_id):
    return response({"definition": {"parts": [{
        "path": "definition.json",
        "payloadType": "InlineBase64",
        "payload": base64.b64encode(
            json.dumps({"parentAppId": parent_app_id}).encode("utf-8")
        ).decode("ascii"),
    }]}})


class SharedAppsTests(unittest.TestCase):
    def test_audience_memberships_preserve_separate_permissions_under_one_app(self):
        app = {"id": "app", "workspaceId": "workspace", "name": "Sample app"}
        audiences = [
            {**app, "id": "sales", "name": "Sales"},
            {**app, "id": "finance", "name": "Finance"},
        ]

        def access(*permissions):
            return {"accessDetails": [{
                "principal": {"id": "user", "type": "User"},
                "itemAccessDetails": {"permissions": list(permissions)},
            }]}

        with (
            patch.object(shared_apps, "get_json", side_effect=[
                {"itemEntities": [app]},
                access("Read", "Reshare"),
                {"itemEntities": audiences},
                access("Read"),
                access("Read", "Explore"),
            ]),
            patch.object(shared_apps, "get_audience_parent_app_id", return_value="app"),
        ):
            rows = list(shared_apps.get_fabric_rows(Mock()))
        self.assertEqual([row["appType"] for row in rows], ["OrgApp"] * 3)
        self.assertEqual([row["appId"] for row in rows], ["app"] * 3)
        self.assertEqual([row["identifier"] for row in rows], ["user"] * 3)
        self.assertEqual([row["audienceName"] for row in rows], [None, "Sales", "Finance"])
        self.assertEqual(
            [row["appUserAccessRight"] for row in rows], ["Read;Reshare", "Read", "Read;Explore"]
        )
        self.assertEqual(len({
            (row["appId"], row["identifier"], row["audienceId"]) for row in rows
        }), 3)

    def test_main_reuses_one_auth_for_both_apis(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(shared_apps, "OUTPUT_FOLDER", Path(directory)),
            patch.object(shared_apps, "create_auth") as create_auth,
            patch.object(shared_apps, "get_power_bi_rows", return_value=[]) as power_bi,
            patch.object(shared_apps, "get_fabric_rows", return_value=[]) as fabric,
        ):
            shared_apps.main()
        create_auth.assert_called_once_with()
        power_bi.assert_called_once_with(create_auth.return_value)
        fabric.assert_called_once_with(create_auth.return_value)

    def test_decodes_audience_parent_app_id(self):
        audience = {"id": "audience", "workspaceId": "workspace"}
        with patch.object(
            shared_apps.requests, "post", return_value=definition_response("parent")
        ):
            self.assertEqual(shared_apps.get_audience_parent_app_id(Mock(), audience), "parent")

    def test_audience_definition_long_running_operation(self):
        audience = {"id": "audience", "workspaceId": "workspace"}
        with (
            patch.object(shared_apps.requests, "post", return_value=response(
                {}, status=202, headers={"x-ms-operation-id": "operation", "Retry-After": "2"}
            )),
            patch.object(shared_apps.requests, "get", side_effect=[
                response({"status": "Running"}, headers={"Retry-After": "3"}),
                response({"status": "Succeeded"}),
                definition_response("parent"),
            ]) as get,
            patch.object(shared_apps.time, "sleep") as sleep,
        ):
            self.assertEqual(shared_apps.get_audience_parent_app_id(Mock(), audience), "parent")
        self.assertEqual([call.args[0] for call in get.call_args_list], [
            f"{shared_apps.FABRIC_API_URL}/operations/operation",
            f"{shared_apps.FABRIC_API_URL}/operations/operation",
            f"{shared_apps.FABRIC_API_URL}/operations/operation/result",
        ])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 3])

    def test_failed_or_timed_out_audience_definition_is_reported(self):
        audience = {"id": "audience", "workspaceId": "workspace"}
        for status, error in (("Failed", RuntimeError), ("Running", TimeoutError)):
            with (
                self.subTest(status=status),
                patch.object(shared_apps, "MAX_OPERATION_POLLS", 1),
                patch.object(shared_apps.requests, "post", return_value=response(
                    {}, status=202, headers={"x-ms-operation-id": "operation"}
                )),
                patch.object(shared_apps.requests, "get", return_value=response({"status": status})),
                patch.object(shared_apps.time, "sleep"),
                self.assertRaises(error),
            ):
                shared_apps.get_audience_parent_app_id(Mock(), audience)

    def test_missing_definition_or_parent_is_reported(self):
        for result in (
            response({"definition": {"parts": []}}),
            definition_response(None),
        ):
            with (
                self.subTest(result=result),
                patch.object(shared_apps.requests, "post", return_value=result),
                self.assertRaises(ValueError),
            ):
                shared_apps.get_audience_parent_app_id(
                    Mock(), {"id": "audience", "workspaceId": "workspace"}
                )

    def test_parent_is_matched_by_id_in_the_correct_workspace(self):
        apps = [
            {"id": "other", "workspaceId": "workspace", "name": "Wrong app"},
            {"id": "parent", "workspaceId": "workspace", "name": "Correct app"},
            {"id": "parent", "workspaceId": "other-workspace", "name": "Wrong workspace"},
        ]
        with (
            patch.object(shared_apps, "get_json", side_effect=[
                {"itemEntities": apps},
                {"accessDetails": []},
                {"accessDetails": []},
                {"accessDetails": []},
                {"itemEntities": [{"id": "audience", "workspaceId": "workspace", "name": "Sales"}]},
                {"accessDetails": []},
            ]),
            patch.object(shared_apps, "get_audience_parent_app_id", return_value="PARENT"),
        ):
            rows = list(shared_apps.get_fabric_rows(Mock()))
        self.assertEqual(rows[-1]["appName"], "Correct app")
        self.assertEqual(rows[-1]["appId"], "parent")

    def test_unresolved_parent_does_not_replace_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "apps.csv"
            output.write_text("existing inventory", encoding="utf-8")
            with (
                patch.object(shared_apps, "OUTPUT_FOLDER", Path(directory)),
                patch.object(shared_apps, "create_auth"),
                patch.object(shared_apps, "get_json", side_effect=[
                    {"value": []},
                    {"itemEntities": []},
                    {"itemEntities": [{"id": "audience", "workspaceId": "workspace"}]},
                ]),
                patch.object(shared_apps, "get_audience_parent_app_id", return_value="missing"),
                self.assertRaisesRegex(ValueError, "Parent app missing"),
            ):
                shared_apps.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "existing inventory")

    def test_two_audiences_use_their_parent_app_metadata(self):
        app = {
            "id": "parent",
            "workspaceId": "workspace",
            "name": "Sample app",
            "description": "Parent description",
            "lastUpdatedDate": "2026-02-01",
        }
        audiences = [
            {**app, "id": "audience-1", "name": "Sales"},
            {**app, "id": "audience-2", "name": "Finance"},
        ]
        with (
            patch.object(shared_apps, "get_json", side_effect=[
                {"itemEntities": [app]},
                {"accessDetails": []},
                {"itemEntities": audiences},
                {"accessDetails": []},
                {"accessDetails": []},
            ]),
            patch.object(
                shared_apps, "get_audience_parent_app_id", return_value="parent"
            ),
        ):
            rows = list(shared_apps.get_fabric_rows(Mock()))
        self.assertEqual([row["appName"] for row in rows], ["Sample app"] * 3)
        self.assertEqual([row["appType"] for row in rows], ["OrgApp"] * 3)
        self.assertEqual([row["appId"] for row in rows], ["parent"] * 3)
        self.assertEqual([row["audienceName"] for row in rows], [None, "Sales", "Finance"])
        self.assertEqual(
            [row["audienceId"] for row in rows], [None, "audience-1", "audience-2"]
        )

    def test_combines_all_item_types_in_existing_csv_with_shared_auth(self):
        app = {
            "id": "app",
            "workspaceId": "workspace",
            "name": "Power BI app",
            "description": "Original app",
            "publishedBy": "Publisher",
            "lastUpdate": "2026-01-01",
        }
        org_app = {
            "id": "org",
            "workspaceId": "workspace",
            "name": "Org app",
            "description": "Fabric app",
            "lastUpdatedDate": "2026-02-01",
            "creatorPrincipal": {"displayName": "Creator, not publisher"},
        }
        audience = {**org_app, "id": "audience", "name": "Audience"}
        access = {
            "principal": {
                "id": "user",
                "displayName": "User",
                "type": "User",
                "userDetails": {"userPrincipalName": "user@example.com"},
            },
            "itemAccessDetails": {
                "permissions": ["Read", "Reshare"],
                "additionalPermissions": ["ReadAll"],
            },
        }
        group_access = {
            "principal": {"id": "group", "displayName": "Group", "type": "Group"},
            "itemAccessDetails": {"permissions": ["Read"]},
        }
        responses = [
            response({"value": [app]}),
            response({"value": [{
                "identifier": "legacy",
                "appUserAccessRight": "Read",
                "userType": "Member",
            }]}),
            response({"value": []}),
            response({"itemEntities": [org_app], "continuationToken": "next"}),
            response({"accessDetails": [access]}),
            response({"itemEntities": []}),
            response({"itemEntities": [audience]}),
            response({"accessDetails": [group_access]}),
        ]
        auth = Mock()
        auth.get_api_auth_headers.side_effect = lambda scope: {"X-Test-Scope": scope}
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(shared_apps, "OUTPUT_FOLDER", Path(directory)),
                patch.object(shared_apps, "create_auth", return_value=auth) as create_auth,
                patch.object(shared_apps.requests, "get", side_effect=responses) as get,
                patch.object(
                    shared_apps.requests, "post", return_value=definition_response("org")
                ) as post,
            ):
                shared_apps.main()
            with (Path(directory) / "apps.csv").open(encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, shared_apps.CSV_FIELDS)
        self.assertEqual([row["appType"] for row in rows], ["App", "OrgApp", "OrgApp"])
        self.assertEqual(rows[0]["appPublishedBy"], "Publisher")
        self.assertEqual(rows[0]["userType"], "Member")
        self.assertEqual(rows[0]["audienceName"], "")
        self.assertEqual(rows[1]["audienceName"], "")
        self.assertEqual(rows[1]["appUserAccessRight"], "Read;Reshare")
        self.assertEqual(rows[1]["additionalPermissions"], "ReadAll")
        self.assertEqual(rows[1]["emailAddress"], "user@example.com")
        self.assertEqual(rows[1]["graphId"], "user")
        self.assertEqual(rows[1]["appLastUpdate"], "2026-02-01")
        self.assertEqual(rows[1]["appPublishedBy"], "")
        self.assertEqual(rows[2]["appId"], "org")
        self.assertEqual(rows[2]["appName"], "Org app")
        self.assertEqual(rows[2]["audienceId"], "audience")
        self.assertEqual(rows[2]["audienceName"], "Audience")
        self.assertEqual(rows[2]["principalType"], "Group")
        self.assertEqual(rows[2]["emailAddress"], "")
        self.assertEqual(get.call_args_list[2].kwargs["params"]["$skip"], 1000)
        self.assertEqual(
            get.call_args_list[3].args[0], f"{shared_apps.FABRIC_API_URL}/admin/items"
        )
        self.assertEqual(get.call_args_list[5].kwargs["params"]["continuationToken"], "next")
        self.assertEqual(get.call_args_list[5].kwargs["params"]["type"], "OrgApp")
        self.assertEqual(get.call_args_list[6].kwargs["params"]["type"], "OrgAppAudience")
        self.assertIn("/items/audience/users", get.call_args_list[7].args[0])
        self.assertIn("/orgAppAudiences/audience/getDefinition", post.call_args.args[0])
        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"X-Test-Scope": shared_apps.FABRIC_SCOPE},
        )
        for call in get.call_args_list[:3]:
            self.assertEqual(call.kwargs["headers"], {"X-Test-Scope": shared_apps.POWER_BI_SCOPE})
        for call in get.call_args_list[3:]:
            self.assertEqual(call.kwargs["headers"], {"X-Test-Scope": shared_apps.FABRIC_SCOPE})
        create_auth.assert_called_once_with()
        auth.get_api_auth_headers.assert_any_call(scope=shared_apps.POWER_BI_SCOPE)
        auth.get_api_auth_headers.assert_any_call(scope=shared_apps.FABRIC_SCOPE)

    def test_no_access_entries_preserve_item_metadata(self):
        with patch.object(shared_apps, "get_json", side_effect=[
            {"value": [{"id": "app", "name": "App"}]},
            {"value": []},
            {"value": []},
        ]):
            rows = list(shared_apps.get_power_bi_rows(Mock()))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["appId"], "app")
        with patch.object(shared_apps, "get_json", side_effect=[
            {"itemEntities": [{"id": "org", "workspaceId": "workspace", "name": "Org"}]},
            {"accessDetails": []},
            {"itemEntities": []},
        ]):
            rows = list(shared_apps.get_fabric_rows(Mock()))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["appId"], "org")
        self.assertIsNone(rows[0]["identifier"])

    def test_empty_inventory_writes_header(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(shared_apps, "OUTPUT_FOLDER", Path(directory)),
                patch.object(shared_apps, "create_auth"),
                patch.object(shared_apps, "get_json", side_effect=[
                    {"value": []}, {"itemEntities": []}, {"itemEntities": []},
                ]),
            ):
                shared_apps.main()
            with (Path(directory) / "apps.csv").open(encoding="utf-8", newline="") as file:
                self.assertEqual(list(csv.reader(file)), [shared_apps.CSV_FIELDS])

    def test_api_error_does_not_replace_existing_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "apps.csv"
            output.write_text("existing inventory", encoding="utf-8")
            with (
                patch.object(shared_apps, "OUTPUT_FOLDER", Path(directory)),
                patch.object(shared_apps, "create_auth"),
                patch.object(shared_apps.requests, "get", side_effect=[
                    response({"value": []}), response({}, status=403),
                ]),
                self.assertRaises(requests.HTTPError),
            ):
                shared_apps.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "existing inventory")

    def test_throttle_retries_then_succeeds(self):
        with (
            patch.object(shared_apps.requests, "get", side_effect=[
                response({}, status=429, headers={"Retry-After": "2"}),
                response({"value": []}),
            ]) as get,
            patch.object(shared_apps.time, "sleep") as sleep,
        ):
            self.assertEqual(shared_apps.get_json(Mock(), "scope", "url"), {"value": []})
        sleep.assert_called_once_with(2)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["timeout"], 30)

    def test_throttle_retries_are_bounded(self):
        with (
            patch.object(shared_apps.requests, "get", return_value=response({}, status=429)) as get,
            patch.object(shared_apps.time, "sleep") as sleep,
            self.assertRaises(requests.HTTPError),
        ):
            shared_apps.get_json(Mock(), "scope", "url")
        self.assertEqual(get.call_count, shared_apps.MAX_RETRIES + 1)
        self.assertEqual(sleep.call_count, shared_apps.MAX_RETRIES)

    def test_auth_uses_existing_credential_options(self):
        with patch.object(shared_apps, "Auth") as auth:
            shared_apps.create_auth()
            auth.assert_called_once_with()
        with (
            patch.object(shared_apps, "TENANT_ID", "tenant"),
            patch.object(shared_apps, "CLIENT_ID", "client"),
            patch.object(shared_apps, "CLIENT_SECRET", "secret"),
            patch.object(shared_apps, "Auth") as auth,
        ):
            shared_apps.create_auth()
            auth.assert_called_once_with(
                tenant_id="tenant", client_id="client", client_secret="secret"
            )


if __name__ == "__main__":
    unittest.main()
