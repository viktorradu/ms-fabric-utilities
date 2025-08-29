import datetime, requests, csv
from azure.identity import DefaultAzureCredential,AzureAuthorityHosts

input_batch_minutes = 30
input_log_end_date = datetime.date.today() - datetime.timedelta(days=1)
input_log_days = 1

start_date = input_log_end_date - datetime.timedelta(days=input_log_days - 1)
end_date = input_log_end_date

cred = DefaultAzureCredential(
                authority = AzureAuthorityHosts.AZURE_PUBLIC_CLOUD,
                exclude_interactive_browser_credential = False,
                exclude_environment_credential = True,
                exclude_managed_identity_credential = True,
                exclude_powershell_credential = True,
                exclude_developer_cli_credential = True,
                exclude_shared_token_cache_credential = True,
                exclude_cli_credential = True
            )

token = cred.get_token('https://analysis.windows.net/powerbi/api/.default').token

headers = {
            "Authorization":"Bearer " + token,
            "Content-Type": "application/json"
            }

result = []

next_batch = None
while True:
    if next_batch is None:
        range_from = datetime.datetime(year=start_date.year, month=start_date.month, day=start_date.day)
    else:  
        range_from = next_batch

    range_to = range_from + datetime.timedelta(minutes=input_batch_minutes)
    range_to_exclusive = range_to - datetime.timedelta(seconds=1)
    datetime_format = '%Y-%m-%dT%H:%M:%SZ'
    activity_uri = f'https://api.powerbi.com/v1.0/myorg/admin/activityevents?startDateTime=%27{range_from.strftime(datetime_format)}%27&endDateTime=%27{range_to_exclusive.strftime(datetime_format)}%27'
    activities_response = requests.get(activity_uri, headers=headers)
    
    if activities_response.status_code == 200:
        activity_response_json = activities_response.json()
        activities = activity_response_json.get('activityEventEntities')
        ct = activity_response_json.get('continuationToken')
        while ct is not None:
            activity_uri = activity_response_json.get('continuationUri')
            activities_response = requests.get(activity_uri, headers=headers)
            if activities_response.status_code == 200:
                activity_response_json = activities_response.json()
                activities.extend(activity_response_json.get('activityEventEntities'))
                ct = activity_response_json.get('continuationToken')

        print(f'Exported {len(activities)} events. Date: {range_from}')
        result.extend(activities)
    else:
        print(f'Error {activities_response.status_code} getting activities: {activities_response.text}')
        break

    if range_to <= datetime.datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59):
        next_batch = range_to
        batch_start_days = (range_from - datetime.datetime.combine(start_date, datetime.time(0,0,0))).days
        batch_progress = batch_start_days / input_log_days
    else: 
        break

if len(result) > 0:
    print(f'Writing {len(result)} events to a file')
    fields = []
    for event in result:
        for field in event.keys():
            if field not in fields:
                fields.append(field)
    with open('activity.csv', 'w', newline='', encoding="utf-8") as file:
        writer = csv.DictWriter(file,fieldnames=fields,extrasaction='raise', quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writeheader()
        writer.writerows(result)
else:
    print(f'No events found')
