import requests, base64, json, datetime
from azure.identity import DefaultAzureCredential
import labconfig
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

queryMetadata = {
  "formatVersion": "202502",
  "computeEngineSettings": {},
  "gatewayObjectId": labconfig.gatewayId,
  "name": "HardcodedQuery",
  "queryGroups": [],
  "documentLocale": "en-US",
  "queriesMetadata": {
    "categories": {
      "queryId": "e866f883-bb67-496c-a4e8-b1266cef1227",
      "queryName": "categories"
    }
  },
  "connections": [
    {
      "allowUsageThroughGateway": True,
      "kind":"DatabricksMultiCloud",
      "path":"{\"host\":\"" + labconfig.databricksHost + "\",\"httpPath\":\"" + labconfig.databricksHttpPath + "\"}",
      "connectionId":"{\"ClusterId\":\"" + labconfig.gatewayId + "\",\"DatasourceId\":\"" + labconfig.databricksConnectionId + "\"}"
    }
  ]
}

mashup = '''[StagingDefinition = [Kind = "FastCopy"]]
section Section1;
shared categories = let
  Source = DatabricksMultiCloud.Catalogs("''' + labconfig.databricksHost + '''", "''' + labconfig.databricksHttpPath + '''", [Catalog = null, Database = null, EnableAutomaticProxyDiscovery = "enabled"]),
  #"Navigation 1" = Source{[Name = "fabricsource", Kind = "Database"]}[Data],
  #"Navigation 2" = #"Navigation 1"{[Name = "default", Kind = "Schema"]}[Data],
  #"Navigation 3" = #"Navigation 2"{[Name = "categories", Kind = "Table"]}[Data],
  #"Renamed columns" = Table.RenameColumns(#"Navigation 3", {{" Product", "Product"}})
in
  #"Renamed columns";
'''

platform = {
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
  "metadata": {
    "type": "Dataflow",
    "displayName": f"Programmatically Created Dataflow {datetime.datetime.now().strftime('%Y-%m-%d %H%M%S')}",
  },
  "config": {
    "version": "2.0",
    "logicalId": "00000000-0000-0000-0000-000000000000"
  }
}

dataflowDefinition = {
  "definition": {
    "parts": [
      {
        "path": "queryMetadata.json",
        "payload": base64.b64encode(json.dumps(queryMetadata).encode('utf-8')).decode('utf-8'),
        "payloadType": "InlineBase64"
      },
      {
        "path": "mashup.pq",
        "payload": base64.b64encode(mashup.encode('utf-8')).decode('utf-8'),
        "payloadType": "InlineBase64"
      },
      {
        "path": ".platform",
        "payload": base64.b64encode(json.dumps(platform).encode('utf-8')).decode('utf-8'),
        "payloadType": "InlineBase64"
      }
    ]
  }
}

created = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{labconfig.workspaceId}/dataflows", headers=headers, json=dataflowDefinition)

if created.status_code != 201:
    print(f"Error creating dataflow: {created.status_code} - {created.text}")
    exit(1)

published = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{labconfig.workspaceId}/dataflows/{created.json().get('id')}/jobs/instances?jobType=ApplyChanges", headers=headers)

if published.status_code != 202:
    print(f"Error publishing dataflow: {published.status_code} - {published.text}")
    exit(1)
