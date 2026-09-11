import csv
from pathlib import Path
from urllib.parse import quote

import requests

from lib.auth import Auth


GRAPH_URL = "https://graph.microsoft.com/v1.0"
USERS_FILE = Path(__file__).with_name("users.txt")
OUTPUT_FILE = Path(__file__).with_name("user-groups.csv")

#Service principal authentication
TENANT_ID = None
CLIENT_ID = None
CLIENT_SECRET = None


def read_users():
    with USERS_FILE.open(encoding="utf-8") as users_file:
        return [
            line.strip()
            for line in users_file
            if line.strip() and not line.lstrip().startswith("#")
        ]


def get_user_groups(session, upn):
    encoded_upn = quote(upn, safe="")
    url = (
        f"{GRAPH_URL}/users/{encoded_upn}/memberOf/microsoft.graph.group"
        "?$select=id,displayName,mail,mailEnabled,securityEnabled"
    )

    while url:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        page = response.json()
        yield from page.get("value", [])
        url = page.get("@odata.nextLink")


def main():
	if all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
		auth = Auth(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
	else:
		auth = Auth()

	with requests.Session() as session:
		session.headers.update(
			auth.get_api_auth_headers("https://graph.microsoft.com/.default")
		)
		session.headers["Accept"] = "application/json"

		with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as output:
			writer = csv.DictWriter(
				output,
				fieldnames=[
					"userPrincipalName",
					"groupId",
					"groupDisplayName",
					"groupMail",
					"mailEnabled",
					"securityEnabled",
				],
			)
			writer.writeheader()

			for upn in read_users():
				for group in get_user_groups(session, upn):
					writer.writerow(
						{
							"userPrincipalName": upn,
							"groupId": group.get("id", ""),
							"groupDisplayName": group.get("displayName", ""),
							"groupMail": group.get("mail", ""),
							"mailEnabled": group.get("mailEnabled", ""),
							"securityEnabled": group.get("securityEnabled", ""),
						}
					)

	print(f"User group memberships written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
