from lib.auth import Auth
from lib.encryption import encrypt_with_public_key
import requests, json

input_gateway_id = "your_gateway_id_here"  # Replace with your actual gateway ID
input_datasource_name = "Azure SQL via OAuth2"  # Replace with your desired datasource name
input_server = "your_server_here"  # Example: myserver.database.windows.net
input_database = "your_database_here"  # Example: mydatabase

pbi_scope = "https://analysis.windows.net/powerbi/api/.default"
db_scope = "https://database.windows.net/.default"

auth = Auth()

gateway = requests.get(
	f"https://api.powerbi.com/v1.0/myorg/gateways/{input_gateway_id}",
	headers=auth.get_api_auth_headers(scope=pbi_scope)
)
public_key_def = gateway.json().get("publicKey")

# Step 1: Create datasource with Anonymous credentials first
anon_creds = {
	"credentialData": []
}
encrypted_anon = encrypt_with_public_key(public_key_def, json.dumps(anon_creds))

create_body = {
	"datasourceType": "Sql",
	"connectionDetails": json.dumps({
		"server": input_server,
		"database": input_database
	}),
	"datasourceName": input_datasource_name,
	"credentialDetails": {
        "credentialType": "Anonymous",
        "credentials": encrypted_anon,
        "encryptedConnection": "Encrypted",
        "encryptionAlgorithm": "RSA-OAEP",
        "privacyLevel": "Organizational",
		"skipTestConnection": True
	}
}

print("Step 1: Creating datasource with Anonymous credentials...")
response = requests.post(
	f"https://api.powerbi.com/v1.0/myorg/gateways/{input_gateway_id}/datasources",
	headers=auth.get_api_auth_headers(scope=pbi_scope),
	json=create_body
)

if response.status_code != 201:
	print(f"Failed to create datasource. Status code: {response.status_code}")
	print(f"Response: {response.text}")
	exit(1)

datasource_id = response.json().get("id")
print(f"Datasource created with ID: {datasource_id}")

# Step 2: Update credentials to OAuth2
oauth_creds = {
	"credentialData": [
		{"name": "accessToken", "value": auth.get_access_token(scope=db_scope)}
	]
}
encrypted_oauth = encrypt_with_public_key(public_key_def, json.dumps(oauth_creds))

update_body = {
	"credentialDetails": {
		"credentialType": "OAuth2",
		"credentials": encrypted_oauth,
		"encryptedConnection": "Encrypted",
		"encryptionAlgorithm": "RSA-OAEP",
		"privacyLevel": "Organizational",
		"useEndUserOAuth2Credentials": "False"
	}
}

print("Step 2: Updating to OAuth2 credentials...")
update_response = requests.patch(
	f"https://api.powerbi.com/v1.0/myorg/gateways/{input_gateway_id}/datasources/{datasource_id}",
	headers=auth.get_api_auth_headers(scope=pbi_scope),
	json=update_body
)

if update_response.status_code == 200:
	print("Datasource created and configured with OAuth2 successfully.")
else:
	print(f"Failed to update credentials. Status code: {update_response.status_code}")
	print(f"Response: {update_response.text}")
