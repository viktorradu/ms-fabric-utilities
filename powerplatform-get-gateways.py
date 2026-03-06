from lib.auth import Auth
import requests, csv

auth = Auth()
pbi_scope = "https://analysis.windows.net/powerbi/api/.default"
headers = auth.get_api_auth_headers(scope=pbi_scope)

response = requests.get("https://api.powerbi.com/v2.0/myorg/gatewayClusters?$expand=memberGateways", headers=headers)
gateways = response.json().get("value", [])
fields = list({k for g in gateways for k in g.keys()})

with open('gateways.csv', 'w', newline='', encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fields, extrasaction='raise', quoting=csv.QUOTE_ALL, lineterminator='\n')
    writer.writeheader()
    writer.writerows(gateways)