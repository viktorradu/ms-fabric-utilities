from lib.auth import Auth
import base64
import csv
import json
import time
from pathlib import Path

import requests

OUTPUT_FOLDER = Path("./output")
OUTPUT_FILE_NAME = "apps.csv"
POWER_BI_API_URL = "https://api.powerbi.com/v1.0/myorg"
FABRIC_API_URL = "https://api.fabric.microsoft.com/v1"
POWER_BI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
BATCH_SIZE = 1000
MAX_RETRIES = 5
MAX_OPERATION_POLLS = 60
REQUEST_TIMEOUT_SECONDS = 30
CSV_FIELDS = [
    "appUserAccessRight",
    "emailAddress",
    "displayName",
    "identifier",
    "graphId",
    "principalType",
    "userType",
    "workspaceId",
    "appName",
    "appDescription",
    "appId",
    "appPublishedBy",
    "appLastUpdate",
    "appType",
    "additionalPermissions",
    "audienceName",
    "audienceId",
]

# Service principal authentication
TENANT_ID = None
CLIENT_ID = None
CLIENT_SECRET = None

def create_auth():
    if all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        return Auth(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
    return Auth()


def request_response(auth, scope, url, params=None, method="GET"):
    for attempt in range(MAX_RETRIES + 1):
        request = {"GET": requests.get, "POST": requests.post}[method]
        response = request(
            url,
            headers=auth.get_api_auth_headers(scope=scope),
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response
        if attempt == MAX_RETRIES:
            response.raise_for_status()
        retry_after = int(response.headers.get("Retry-After", 60))
        print(f"Rate limit encountered. Retrying after {retry_after} seconds.")
        time.sleep(retry_after)

    raise RuntimeError(f"Failed to get a response from {url}")


def get_json(auth, scope, url, params=None):
    return request_response(auth, scope, url, params=params).json()


def get_audience_parent_app_id(auth, audience):
    url = (
        f"{FABRIC_API_URL}/workspaces/{audience['workspaceId']}"
        f"/orgAppAudiences/{audience['id']}/getDefinition"
    )
    response = request_response(auth, FABRIC_SCOPE, url, method="POST")
    if response.status_code == 202:
        operation_url = f"{FABRIC_API_URL}/operations/{response.headers['x-ms-operation-id']}"
        for _ in range(MAX_OPERATION_POLLS):
            time.sleep(int(response.headers.get("Retry-After", 1)))
            response = request_response(auth, FABRIC_SCOPE, operation_url)
            operation = response.json()
            status = operation["status"]
            if status == "Succeeded":
                response = request_response(auth, FABRIC_SCOPE, f"{operation_url}/result")
                break
            if status not in ("NotStarted", "Running"):
                raise RuntimeError(
                    f"Audience definition operation for {audience['id']} "
                    f"ended with {status}: {operation.get('error')}"
                )
        else:
            raise TimeoutError(f"Audience definition operation timed out for {audience['id']}")

    for part in response.json()["definition"]["parts"]:
        if part["path"] == "definition.json":
            if part["payloadType"] != "InlineBase64":
                raise ValueError(f"Unsupported audience definition payload for {audience['id']}")
            definition = json.loads(base64.b64decode(part["payload"], validate=True))
            parent_app_id = definition.get("parentAppId")
            if not isinstance(parent_app_id, str) or not parent_app_id:
                raise ValueError(f"Audience {audience['id']} has no valid parentAppId")
            return parent_app_id
    raise ValueError(f"Audience {audience['id']} has no definition.json part")


def get_fabric_values(auth, url, key, params=None):
    params = dict(params or {})
    while True:
        page = get_json(auth, FABRIC_SCOPE, url, params=params)
        yield from page[key]
        continuation_token = page.get("continuationToken")
        if not continuation_token:
            break
        params["continuationToken"] = continuation_token


def get_power_bi_rows(auth):
    skip = 0
    while True:
        page = get_json(
            auth,
            POWER_BI_SCOPE,
            f"{POWER_BI_API_URL}/admin/apps",
            params={"$top": BATCH_SIZE, "$skip": skip},
        )
        apps = page["value"]
        if not apps:
            break
        for app in apps:
            users = get_json(
                auth,
                POWER_BI_SCOPE,
                f"{POWER_BI_API_URL}/admin/apps/{app['id']}/users",
            )["value"]
            for user in users or [{}]:
                yield {
                    **user,
                    "workspaceId": app.get("workspaceId"),
                    "appName": app.get("name"),
                    "appDescription": app.get("description"),
                    "appId": app["id"],
                    "appPublishedBy": app.get("publishedBy"),
                    "appLastUpdate": app.get("lastUpdate"),
                    "appType": "App",
                }
        skip += BATCH_SIZE


def get_fabric_rows(auth):
    apps_by_id = {}
    for item_type in ("OrgApp", "OrgAppAudience"):
        items = get_fabric_values(
            auth,
            f"{FABRIC_API_URL}/admin/items",
            "itemEntities",
            params={"type": item_type},
        )
        for item in items:
            if item_type == "OrgApp":
                apps_by_id[(item["workspaceId"].casefold(), item["id"].casefold())] = item
                app = item
            else:
                parent_app_id = get_audience_parent_app_id(auth, item)
                app = apps_by_id.get((item["workspaceId"].casefold(), parent_app_id.casefold()))
                if app is None:
                    raise ValueError(
                        f"Parent app {parent_app_id} for audience {item['id']} "
                        f"was not found in workspace {item['workspaceId']}"
                    )
            access_details = list(get_fabric_values(
                auth,
                f"{FABRIC_API_URL}/admin/workspaces/{item['workspaceId']}"
                f"/items/{item['id']}/users",
                "accessDetails",
            ))
            for access in access_details or [{}]:
                principal = access.get("principal", {})
                user_details = principal.get("userDetails", {})
                permissions = access.get("itemAccessDetails", {})
                yield {
                    "appUserAccessRight": ";".join(permissions.get("permissions", [])),
                    "additionalPermissions": ";".join(
                        permissions.get("additionalPermissions", [])
                    ),
                    "emailAddress": user_details.get("userPrincipalName"),
                    "displayName": principal.get("displayName"),
                    "identifier": principal.get("id"),
                    "graphId": principal.get("id"),
                    "principalType": principal.get("type"),
                    "workspaceId": item["workspaceId"],
                    "appName": app.get("name"),
                    "audienceName": item.get("name") if item_type == "OrgAppAudience" else None,
                    "audienceId": item["id"] if item_type == "OrgAppAudience" else None,
                    "appDescription": app.get("description"),
                    "appId": app["id"],
                    "appType": "OrgApp",
                    "appLastUpdate": app.get("lastUpdatedDate"),
                }


def main():
    auth = create_auth()
    rows = list(get_power_bi_rows(auth))
    rows.extend(get_fabric_rows(auth))

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_FOLDER / OUTPUT_FILE_NAME
    with output_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    item_count = len({
        (row["appType"], row["workspaceId"], row["appId"])
        for row in rows
    })
    print(f"Finished fetching {item_count} apps and their users and audience memberships.")
    print(f"CSV file written to {output_file}")


if __name__ == "__main__":
    main()