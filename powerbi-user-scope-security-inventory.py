import base64
import csv
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import requests

from lib.auth import Auth


POWER_BI_API_URL = "https://api.powerbi.com/v1.0/myorg"
POWER_BI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
CAPACITIES_FILE = Path(__file__).with_name("capacities.txt")
OUTPUT_FOLDER = Path("./output")
REQUEST_TIMEOUT_SECONDS = 30
WORKSPACE_PAGE_SIZE = 5000
MAX_RETRIES = 5
ROLE_MEMBER_TYPE_NAMES = {
    "1": "Auto",
    "2": "User",
    "3": "Group",
}
ADOMD_CLIENT_DLL = Path(
    "C:/Program Files/Microsoft Power BI Desktop/bin/"
    "Microsoft.PowerBI.AdomdClient.dll"
)
XMLA_TENANT = None

# Service principal authentication
TENANT_ID = None
CLIENT_ID = None
CLIENT_SECRET = None

WORKSPACE_ACCESS_FIELDS = [
    "capacityId",
    "workspaceId",
    "workspaceName",
    "workspaceType",
    "workspaceState",
    "principalId",
    "displayName",
    "emailAddress",
    "identifier",
    "principalType",
    "workspaceUserAccessRight",
    "profileId",
    "profileDisplayName",
]

SEMANTIC_MODEL_ACCESS_FIELDS = [
    "capacityId",
    "workspaceId",
    "workspaceName",
    "semanticModelId",
    "semanticModelName",
    "principalId",
    "displayName",
    "emailAddress",
    "identifier",
    "principalType",
    "semanticModelUserAccessRight",
    "roleName",
    "modelPermission",
    "identityProvider",
    "profileId",
    "profileDisplayName",
]


def read_capacity_ids():
    capacity_ids = []

    with CAPACITIES_FILE.open(encoding="utf-8-sig") as capacities_file:
        for line_number, line in enumerate(capacities_file, start=1):
            capacity_id = line.strip()
            if not capacity_id or capacity_id.startswith("#"):
                continue

            try:
                capacity_ids.append(str(UUID(capacity_id)))
            except ValueError as error:
                raise ValueError(
                    f"Invalid capacity ID on line {line_number} of "
                    f"{CAPACITIES_FILE}: {capacity_id}"
                ) from error

    if not capacity_ids:
        raise ValueError(f"No capacity IDs found in {CAPACITIES_FILE}")

    return capacity_ids


def request_json(session, method, url, params=None, json=None):
    for attempt in range(MAX_RETRIES + 1):
        response = session.request(
            method,
            url,
            params=params,
            json=json,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if response.status_code != 429:
            response.raise_for_status()
            return response.json()

        if attempt == MAX_RETRIES:
            response.raise_for_status()

        retry_after = int(response.headers.get("Retry-After", 60))
        print(f"Rate limit encountered. Retrying after {retry_after} seconds.")
        time.sleep(retry_after)

    raise RuntimeError(f"Failed to get a response from {url}")


def get_json(session, url, params=None):
    return request_json(session, "GET", url, params=params)


def get_all_values(session, url, params=None):
    while url:
        page = get_json(session, url, params=params)
        yield from page.get("value", [])
        url = page.get("@odata.nextLink")
        params = None


def get_group_display_name(session, group_id, group_names_by_id):
    cache_key = group_id.casefold()
    if cache_key not in group_names_by_id:
        encoded_group_id = quote(group_id, safe="")
        group = get_json(
            session,
            f"{GRAPH_API_URL}/groups/{encoded_group_id}",
            params={"$select": "displayName"},
        )
        display_name = group.get("displayName")
        if not display_name:
            raise ValueError(
                f"Microsoft Graph returned no display name for group "
                f"{group_id}"
            )
        group_names_by_id[cache_key] = display_name

    return group_names_by_id[cache_key]


def get_workspaces(session, capacity_ids):
    skip = 0

    while True:
        page = get_json(
            session,
            f"{POWER_BI_API_URL}/groups",
            params={
                "$top": WORKSPACE_PAGE_SIZE,
                "$skip": skip,
            },
        )
        workspaces = page.get("value", [])

        for workspace in workspaces:
            capacity_id = workspace.get("capacityId", "").lower()
            if capacity_id in capacity_ids:
                yield workspace

        if len(workspaces) < WORKSPACE_PAGE_SIZE:
            break

        skip += WORKSPACE_PAGE_SIZE


def flatten_principal(principal):
    profile = principal.get("profile") or {}
    return {
        "principalId": principal.get("graphId", ""),
        "displayName": principal.get("displayName", ""),
        "emailAddress": principal.get("emailAddress", ""),
        "identifier": principal.get("identifier", ""),
        "principalType": principal.get("principalType", ""),
        "profileId": profile.get("id", ""),
        "profileDisplayName": profile.get("displayName", ""),
    }


def load_adomd_connection_type():
    if not ADOMD_CLIENT_DLL.is_file():
        raise FileNotFoundError(
            f"ADOMD client library not found at {ADOMD_CLIENT_DLL}. "
            "Set ADOMD_CLIENT_DLL to the installed Analysis Services "
            "ADOMD client library."
        )

    try:
        import clr
    except ImportError as error:
        raise RuntimeError(
            "The pythonnet package is required to query RLS metadata "
            "through the XMLA endpoint."
        ) from error

    assembly_folder = str(ADOMD_CLIENT_DLL.parent)
    if assembly_folder not in sys.path:
        sys.path.insert(0, assembly_folder)

    clr.AddReference(str(ADOMD_CLIENT_DLL))
    from Microsoft.AnalysisServices.AdomdClient import AdomdConnection

    return AdomdConnection


def escape_connection_string_value(value):
    return '"' + str(value).replace('"', '""') + '"'


def decode_access_token_payload(access_token):
    try:
        encoded_payload = access_token.split(".")[1]
        encoded_payload += "=" * (-len(encoded_payload) % 4)
        return json.loads(
            base64.urlsafe_b64decode(encoded_payload).decode("utf-8")
        )
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError(
            "Could not decode the Power BI access token"
        ) from error


def create_adomd_access_token(access_token):
    payload = decode_access_token_payload(access_token)
    try:
        expiration = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "Could not read the expiration from the Power BI access token"
        ) from error

    from Microsoft.AnalysisServices.AdomdClient import AccessToken
    from System import DateTimeOffset

    return AccessToken(
        access_token,
        DateTimeOffset.FromUnixTimeSeconds(expiration),
        None,
    )


def read_dmv(connection, query):
    command = connection.CreateCommand()
    command.CommandText = query
    reader = command.ExecuteReader()

    try:
        rows = []
        column_names = [
            reader.GetName(index) for index in range(reader.FieldCount)
        ]

        while reader.Read():
            rows.append(
                {
                    column_name: reader.GetValue(index)
                    for index, column_name in enumerate(column_names)
                }
            )

        return rows
    finally:
        reader.Close()
        command.Dispose()


def get_rls_role_memberships(
    adomd_connection_type,
    access_token,
    xmla_tenant,
    workspace_name,
    semantic_model_name,
):
    tenant_path = quote(xmla_tenant, safe="")
    workspace_path = quote(workspace_name, safe="")
    connection_string = (
        "Data Source=powerbi://api.powerbi.com/v1.0/"
        f"{tenant_path}/"
        f"{workspace_path};"
        "Initial Catalog="
        f"{escape_connection_string_value(semantic_model_name)};"
    )
    connection = adomd_connection_type(connection_string)
    if access_token is not None:
        connection.AccessToken = create_adomd_access_token(access_token)

    try:
        connection.Open()
        roles = read_dmv(
            connection,
            "SELECT [ID], [Name], [ModelPermission] "
            "FROM $SYSTEM.TMSCHEMA_ROLES",
        )
        memberships = read_dmv(
            connection,
            "SELECT [RoleID], [MemberName], [MemberID], "
            "[MemberType], [IdentityProvider] "
            "FROM $SYSTEM.TMSCHEMA_ROLE_MEMBERSHIPS",
        )
    finally:
        connection.Close()
        connection.Dispose()

    roles_by_id = {
        str(role["ID"]): role
        for role in roles
    }
    role_memberships = []

    for membership in memberships:
        role = roles_by_id.get(str(membership["RoleID"]))
        if role is None:
            raise RuntimeError(
                "RLS role membership references an unknown role ID "
                f"{membership['RoleID']}"
            )

        role_memberships.append(
            {
                "roleName": str(role["Name"]),
                "modelPermission": str(role["ModelPermission"]),
                "memberId": str(membership["MemberID"]),
                "memberName": str(membership["MemberName"]),
                "memberType": get_role_member_type_name(
                    membership["MemberType"]
                ),
                "identityProvider": str(membership["IdentityProvider"]),
            }
        )

    return role_memberships


def principal_lookup_keys(principal):
    return {
        str(value).casefold()
        for value in (
            principal.get("graphId"),
            principal.get("identifier"),
            principal.get("emailAddress"),
        )
        if value
    }


def get_role_member_type_name(member_type):
    member_type_value = str(member_type)
    if member_type_value in ROLE_MEMBER_TYPE_NAMES.values():
        return member_type_value

    try:
        return ROLE_MEMBER_TYPE_NAMES[member_type_value]
    except KeyError as error:
        raise ValueError(
            f"Unknown Analysis Services role member type: {member_type_value}"
        ) from error


def write_workspace_access(session, writer, capacity_id, workspace):
    workspace_id = workspace["id"]
    users_url = f"{POWER_BI_API_URL}/groups/{workspace_id}/users"
    user_count = 0

    for user in get_all_values(session, users_url):
        user_count += 1
        writer.writerow(
            {
                "capacityId": capacity_id,
                "workspaceId": workspace_id,
                "workspaceName": workspace.get("name", ""),
                "workspaceType": workspace.get("type", ""),
                "workspaceState": workspace.get("state", ""),
                **flatten_principal(user),
                "workspaceUserAccessRight": user.get(
                    "groupUserAccessRight", ""
                ),
            }
        )

    return user_count


def write_semantic_model_access(
    session,
    graph_session,
    writer,
    capacity_id,
    workspace,
    access_token,
    adomd_connection_type,
    xmla_tenant,
    group_names_by_id,
):
    workspace_id = workspace["id"]
    semantic_models_url = (
        f"{POWER_BI_API_URL}/groups/{workspace_id}/datasets"
    )
    rls_semantic_model_count = 0
    role_assignment_count = 0

    for semantic_model in get_all_values(session, semantic_models_url):
        semantic_model_id = semantic_model["id"]
        semantic_model_name = semantic_model.get("name", "")

        if not semantic_model.get("isEffectiveIdentityRolesRequired", False):
            print(
                f"    Skipping semantic model {semantic_model_name} "
                f"({semantic_model_id}): RLS is not configured"
            )
            continue

        rls_semantic_model_count += 1
        print(
            f"    Reading RLS roles for semantic model "
            f"{semantic_model_name} ({semantic_model_id})"
        )
        role_memberships = get_rls_role_memberships(
            adomd_connection_type,
            access_token,
            xmla_tenant,
            workspace.get("name", ""),
            semantic_model_name,
        )
        print(
            f"    Reading permissions for RLS semantic model "
            f"{semantic_model_name}"
        )
        users_url = (
            f"{POWER_BI_API_URL}/groups/{workspace_id}/datasets/"
            f"{semantic_model_id}/users"
        )
        users = list(get_all_values(session, users_url))
        users_by_key = {}

        for user in users:
            for key in principal_lookup_keys(user):
                users_by_key[key] = user

        for membership in role_memberships:
            member_keys = {
                membership["memberId"].casefold(),
                membership["memberName"].casefold(),
            }
            user = next(
                (
                    users_by_key[key]
                    for key in member_keys
                    if key in users_by_key
                ),
                {},
            )
            principal = flatten_principal(user)
            principal["principalId"] = (
                principal["principalId"] or membership["memberId"]
            )
            principal["identifier"] = (
                principal["identifier"] or membership["memberName"]
            )
            if (
                not principal["displayName"]
                and membership["memberType"] == "Group"
            ):
                principal["displayName"] = get_group_display_name(
                    graph_session,
                    membership["memberId"],
                    group_names_by_id,
                )
            principal["displayName"] = (
                principal["displayName"] or membership["memberName"]
            )
            principal["principalType"] = (
                principal["principalType"] or membership["memberType"]
            )

            writer.writerow(
                {
                    "capacityId": capacity_id,
                    "workspaceId": workspace_id,
                    "workspaceName": workspace.get("name", ""),
                    "semanticModelId": semantic_model_id,
                    "semanticModelName": semantic_model_name,
                    **principal,
                    "semanticModelUserAccessRight": user.get(
                        "datasetUserAccessRight", ""
                    ),
                    "roleName": membership["roleName"],
                    "modelPermission": membership["modelPermission"],
                    "identityProvider": membership["identityProvider"],
                }
            )

            role_assignment_count += 1

    return rls_semantic_model_count, role_assignment_count


def main():
    print(f"Reading capacity IDs from {CAPACITIES_FILE}")
    capacity_ids = read_capacity_ids()
    print(f"Loaded {len(capacity_ids)} capacity IDs")

    print(f"Preparing output folder {OUTPUT_FOLDER}")
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    use_service_principal = all(
        [TENANT_ID, CLIENT_ID, CLIENT_SECRET]
    )
    if use_service_principal:
        print("Configuring service principal authentication")
        auth = Auth(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
    else:
        print("Configuring interactive authentication")
        auth = Auth()

    workspace_access_file = OUTPUT_FOLDER / "workspace-access.csv"
    semantic_model_access_file = (
        OUTPUT_FOLDER / "semantic-model-access.csv"
    )

    with (
        requests.Session() as session,
        requests.Session() as graph_session,
        workspace_access_file.open(
            "w", newline="", encoding="utf-8-sig"
        ) as workspace_access_output,
        semantic_model_access_file.open(
            "w", newline="", encoding="utf-8-sig"
        ) as semantic_model_access_output,
    ):
        print("Authenticating with the Power BI API")
        session.headers.update(auth.get_api_auth_headers(POWER_BI_SCOPE))
        session.headers["Accept"] = "application/json"
        print("Authenticating with Microsoft Graph")
        graph_access_token = auth.get_access_token(GRAPH_SCOPE)
        graph_session.headers.update(
            {
                "Authorization": f"Bearer {graph_access_token}",
                "Accept": "application/json",
            }
        )
        print("Authentication completed")
        token_payload = decode_access_token_payload(auth.token)
        xmla_tenant = XMLA_TENANT or token_payload.get("tid")
        if not xmla_tenant:
            raise ValueError(
                "The Power BI access token does not contain a tenant ID. "
                "Set XMLA_TENANT explicitly."
            )
        print(f"XMLA connections will target tenant {xmla_tenant}")

        print(f"Loading ADOMD client library from {ADOMD_CLIENT_DLL}")
        adomd_connection_type = load_adomd_connection_type()
        print("ADOMD client library loaded")
        if use_service_principal:
            xmla_access_token = auth.token
            print("XMLA will use service principal authentication")
        else:
            xmla_access_token = None
            print(
                "XMLA will use ADOMD interactive authentication; "
                "a separate sign-in prompt may appear"
            )

        print("Initializing CSV output files")
        workspace_access_writer = csv.DictWriter(
            workspace_access_output,
            fieldnames=WORKSPACE_ACCESS_FIELDS,
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        semantic_model_access_writer = csv.DictWriter(
            semantic_model_access_output,
            fieldnames=SEMANTIC_MODEL_ACCESS_FIELDS,
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        workspace_access_writer.writeheader()
        semantic_model_access_writer.writeheader()

        workspace_count = 0
        workspace_user_count = 0
        rls_semantic_model_count = 0
        role_assignment_count = 0
        group_names_by_id = {}
        capacity_id_set = set(capacity_ids)
        print("Listing accessible workspaces")

        for workspace in get_workspaces(session, capacity_id_set):
            capacity_id = workspace["capacityId"].lower()
            workspace_count += 1
            workspace_name = workspace.get("name", "")
            workspace_id = workspace["id"]
            print(
                f"Reading workspace {workspace_name} ({workspace_id})"
            )
            print("  Reading workspace users")
            current_workspace_user_count = write_workspace_access(
                session,
                workspace_access_writer,
                capacity_id,
                workspace,
            )
            workspace_user_count += current_workspace_user_count
            print(
                f"  Wrote {current_workspace_user_count} workspace users"
            )

            print("  Reading semantic models")
            (
                current_rls_semantic_model_count,
                current_role_assignment_count,
            ) = write_semantic_model_access(
                session,
                graph_session,
                semantic_model_access_writer,
                capacity_id,
                workspace,
                xmla_access_token,
                adomd_connection_type,
                xmla_tenant,
                group_names_by_id,
            )
            rls_semantic_model_count += current_rls_semantic_model_count
            role_assignment_count += current_role_assignment_count
            print(
                f"  Wrote {current_role_assignment_count} role "
                f"assignments for {current_rls_semantic_model_count} "
                "RLS semantic models"
            )

    print(
        f"Finished reading {workspace_count} workspaces, "
        f"{workspace_user_count} workspace users, "
        f"{rls_semantic_model_count} RLS semantic models, and "
        f"{role_assignment_count} RLS role assignments."
    )
    print(f"CSV files written to {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()