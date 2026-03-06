from lib.auth import Auth
import requests, labconfig

auth = Auth(
    tenant_id=labconfig.ta_tenantID,
    client_id=labconfig.ta_clientID,
    client_secret=labconfig.ta_clientSecret
)
headers = auth.get_api_auth_headers(scope="https://analysis.windows.net/powerbi/api/.default")

request = {
    "capacityMigrationAssignments": [
        {
            "workspacesToAssign": ['56a7d71b-658f-4587-ab31-a6c09968e9c7'],
            "targetCapacityObjectId": "0453190C-08FD-4AA3-9ECF-3FB3FF01EF2C"
        }
    ]
}

response = requests.post("https://api.powerbi.com/v1.0/myorg/admin/capacities/AssignWorkspaces", headers=headers, json=request)


print(response.status_code)
print(response.json())