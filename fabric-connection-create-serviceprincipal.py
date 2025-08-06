import requests
from azure.identity import DefaultAzureCredential
import labconfig
import json
from lib.encryption import encrypt_with_public_key


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