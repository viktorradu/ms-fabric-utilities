import requests
from azure.identity import DefaultAzureCredential
import labconfig
import json, base64, os
from authenticatedencryption import AuthenticatedEncryption
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

def encrypt_with_public_key(public_key: dict, data: str) -> str:
    modulus_bytes = base64.b64decode(public_key['modulus'])
    exponent_bytes = base64.b64decode(public_key['exponent'])
    public_key = rsa.RSAPublicNumbers(
        int.from_bytes(exponent_bytes, 'big'),
        int.from_bytes(modulus_bytes, 'big')
    ).public_key(default_backend())

    key_enc = os.urandom(32)
    key_mac = os.urandom(64)
    
    cipher_text = AuthenticatedEncryption().encrypt(key_enc, key_mac, data.encode('utf-8'))

    keys = bytearray([0] * (len(key_enc) + len(key_mac) + 2))

    keys[0] = 0
    keys[1] = 1

    keys[2: len(key_enc) + 2] = key_enc[0: len(key_enc)]
    keys[len(key_enc) + 2: len(key_enc) + len(key_mac) + 2] = key_mac[0: len(key_mac)]

    encrypted_bytes = public_key.encrypt(bytes(keys),
                                             padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                                                          algorithm=hashes.SHA256(),
                                                          label=None))

    return base64.b64encode(encrypted_bytes).decode() + base64.b64encode(cipher_text).decode()


auth = DefaultAzureCredential(
    exclude_interactive_browser_credential=False,
    exclude_managed_identity_credential = True,
    exclude_environment_credential = True,
    exclude_workload_identity_credential = True,
    exclude_developer_cli_credential = True,
    exclude_shared_token_cache_credential = True,
    exclude_cli_credential = True,
    exclude_powershell_credential = True
)

token = auth.get_token("https://analysis.windows.net/powerbi/api/.default")
headers = {
            "Authorization":"Bearer " + token.token,
            "Content-Type": "application/json"
            }

gatewayInfo = requests.get(f"https://api.fabric.microsoft.com/v1/gateways/{labconfig.gatewayId}", headers=headers)
if gatewayInfo.status_code != 200:
    print(f"Failed to retrieve gateway information. Status code: {gatewayInfo.status_code}")
    print(f"Response: {gatewayInfo.text}")
    exit(1) 

publicKeyDefinition = gatewayInfo.json().get("publicKey")

creds = {
    "credentialData":[
        {"name":"tenantId","value":labconfig.tenantId},
        {"name":"servicePrincipalClientId","value":labconfig.servicePrincipalId},
        {"name":"servicePrincipalSecret","value":labconfig.servicePrincipalSecret}
    ]
}

encryptedCredentials = encrypt_with_public_key(publicKeyDefinition, json.dumps(creds)) 

connectionBody = {
    "connectivityType": "OnPremisesGateway",
    "gatewayId": labconfig.gatewayId,
    "dataSourceType": "SQL",
    "displayName": "Automated Connection with SP", 
    "connectionDetails": {
        "type": "SQL",
        "creationMethod": "SQL",
        "parameters": [
            {
                "dataType": "Text",
                "name": "server",
                "value": labconfig.sqlServer
            },
            {
                "dataType": "Text",
                "name": "database",
                "value": labconfig.sqlDatabase
            }
        ]
    },
    "privacyLevel": "Organizational",
    "credentialDetails": {
        "singleSignOnType": "None",
        "connectionEncryption": "Encrypted",
        "credentials": {
            "credentialType": "ServicePrincipal",
            "values": [
                {
                    "gatewayId": labconfig.gatewayId,
                    "encryptedCredentials": encryptedCredentials
                }
            ]
        }
    }
}


result = requests.post(f"https://api.fabric.microsoft.com/v1/connections", data=json.dumps(connectionBody), headers=headers)
if result.status_code == 201:
    print("Data source created successfully.")
else:
    print(f"Failed to create data source. Status code: {result.status_code}")
    print(f"Response: {result.text}")