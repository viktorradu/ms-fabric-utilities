import csv
import time
from pathlib import Path

import requests

from lib.auth import Auth


# Leave all three unset for interactive authentication.
TENANT_ID = None
CLIENT_ID = None
CLIENT_SECRET = None

OUTPUT_FILE = Path("./output/connections.csv")
CONNECTIONS_URL = "https://api.fabric.microsoft.com/v1/admin/connections"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
CSV_FIELDS = [
    "id",
    "displayName",
    "gatewayId",
    "connectivityType",
    "privacyLevel",
    "myRole",
    "allowConnectionUsageInGateway",
    "allowUsageInUserControlledCode",
    "connectionDetails.type",
    "connectionDetails.path",
    "credentialDetails.credentialType",
    "credentialDetails.singleSignOnType",
    "credentialDetails.connectionEncryption",
    "credentialDetails.skipTestConnection",
    "connectionRecency.createdDateTime",
    "connectionRecency.lastBoundDateTime",
    "connectionRecency.lastCredentialUsedDateTime",
    "connectionRecency.myLastBoundDateTime",
    "connectionRecency.myLastCredentialUsedDateTime",
    "ownerIds",
    "ownerTypes",
    "ownerDisplayNames",
    "ownerUserPrincipalNames",
]


def create_auth():
    credentials = [TENANT_ID, CLIENT_ID, CLIENT_SECRET]
    if any(value is not None for value in credentials):
        if not all(credentials):
            raise ValueError(
                "Set TENANT_ID, CLIENT_ID, and CLIENT_SECRET together, "
                "or leave all three as None for interactive authentication."
            )
        return Auth(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
    return Auth()


def get_json(auth, session, url, params):
    for attempt in range(MAX_RETRIES + 1):
        response = session.get(
            url,
            headers=auth.get_api_auth_headers(FABRIC_SCOPE),
            params=params,
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


def get_all_values(auth, session, url):
    params = {}
    while True:
        page = get_json(auth, session, url, params)
        yield from page["value"]
        continuation_token = page.get("continuationToken")
        if not continuation_token:
            break
        params = {"continuationToken": continuation_token}


def get_connections(auth, session):
    return get_all_values(auth, session, CONNECTIONS_URL)


def get_connection_owners(auth, session, connection_id):
    owners = [
        assignment["principal"]
        for assignment in get_all_values(
            auth, session, f"{CONNECTIONS_URL}/{connection_id}/roleAssignments"
        )
        if assignment["role"] == "Owner"
    ]
    return {
        "ownerIds": ";".join(owner["id"] for owner in owners),
        "ownerTypes": ";".join(owner["type"] for owner in owners),
        "ownerDisplayNames": ";".join(owner.get("displayName") or "" for owner in owners),
        "ownerUserPrincipalNames": ";".join(
            (owner.get("userDetails") or {}).get("userPrincipalName") or ""
            for owner in owners
        ),
    }


def flatten_connection(connection):
    row = {}
    for field in CSV_FIELDS:
        parent, separator, child = field.partition(".")
        if separator:
            row[field] = (connection.get(parent) or {}).get(child, "")
        else:
            row[field] = connection.get(field, "")
    return row


def main():
    auth = create_auth()
    with requests.Session() as session:
        rows = []
        for connection in get_connections(auth, session):
            row = flatten_connection(connection)
            row.update(get_connection_owners(auth, session, connection["id"]))
            rows.append(row)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} connections to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
