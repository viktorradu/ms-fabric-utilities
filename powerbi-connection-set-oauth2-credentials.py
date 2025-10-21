from lib.powerbiAuth import PowerBIAuth
from lib.encryption import encrypt_with_public_key
import requests, json

auth = PowerBIAuth()

input_gateway_id = "your_gateway_id_here"  # Replace with your actual gateway ID
input_datasource_id = "your_datasource_id_here"  # Replace with your actual datasource ID
input_token = "your_oauth_token_here"  # Replace with your actual OAuth2 token

gateway = requests.get(f"https://api.powerbi.com/v1.0/myorg/gateways/{input_gateway_id}", headers=auth.get_api_auth_headers())
publicKeyDef = gateway.json().get("publicKey")

creds = {
    "credentialData":[
        {"name":"accessToken","value":input_token}
    ]
}
encrypted_creds = encrypt_with_public_key(publicKeyDef, json.dumps(creds))
updateBody = {
    "credentialDetails": {
      "credentialType": "OAuth2",
      "credentials": encrypted_creds,
      "encryptedConnection": "Encrypted",
      "encryptionAlgorithm": "RSA-OAEP",
      "privacyLevel": "Organizational",
      "useEndUserOAuth2Credentials": "False"
    }
  }

response = requests.patch(f"https://api.powerbi.com/v1.0/myorg/gateways/{input_gateway_id}/datasources/{input_datasource_id}", headers=auth.get_api_auth_headers(), json=updateBody)
if response.status_code == 200:
    print("Credentials updated successfully.") 
else:
    print(f"Failed to update credentials. Status code: {response.status_code}")
    print(f"Response: {response.text}")



