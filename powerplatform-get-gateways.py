from lib.powerbiAuth import PowerBIAuth
import requests, csv

auth = PowerBIAuth()
headers = auth.get_api_auth_headers()

response = requests.get("https://api.powerbi.com/v2.0/myorg/gatewayClusters?$expand=memberGateways", headers=headers)
gateways = response.json().get("value", [])
fields = list({k for g in gateways for k in g.keys()})

with open('gateways.csv', 'w', newline='', encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fields, extrasaction='raise', quoting=csv.QUOTE_ALL, lineterminator='\n')
    writer.writeheader()
    writer.writerows(gateways)