from lib.powerbiAuth import PowerBIAuth
import requests, time, csv

auth = PowerBIAuth()

batch_size = 1000
skip = 0
all_apps = []

while True:
    apps_batch = requests.get(f"https://api.powerbi.com/v1.0/myorg/admin/apps?$top={batch_size}&$skip={skip}", headers=auth.get_api_auth_headers())
    if apps_batch.status_code != 200:
        print("Error fetching apps:", apps_batch.text)
        break

    apps = apps_batch.json().get("value", [])
    if apps:
        all_apps.extend(apps)
        skip += batch_size
    else:
        break

file = "apps.csv"
with open(file, 'w', newline='', encoding="utf-8") as file:
    writer = None
    for app in all_apps:
        while True:
            app_users = requests.get(f"https://api.powerbi.com/v1.0/myorg/admin/apps/{app.get('id')}/users", headers=auth.get_api_auth_headers())
            if app_users.status_code == 200:
                users = app_users.json().get("value", [])
                for user in users:
                    user["appName"] = app.get("name")
                    user["appId"] = app.get("id")
                if writer is None:
                    writer = csv.DictWriter(file, fieldnames=users[0].keys(), extrasaction='ignore', quoting=csv.QUOTE_ALL, lineterminator='\n')
                    writer.writeheader()
                writer.writerows(users)
                break
            elif app_users.status_code == 429:
                retryAfter = int(app_users.headers.get("Retry-After", 60))
                print(f"Rate limit encountered. Continuing after {retryAfter} seconds.")
                time.sleep(retryAfter)
            else:
                print("Error fetching app users:", app_users.text)
                break

print(f"Finished fetching {len(all_apps)} apps and their users.")