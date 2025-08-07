import requests, time

def ensure_LRO_complete(immediate_response, headers):
    circuit_breaker = 0
    while immediate_response.status_code == 202:
        time.sleep(1)
        immediate_response = requests.get(immediate_response.headers.get("Location"), headers=headers)
        circuit_breaker += 1
        if circuit_breaker > 60:
            raise Exception("Long-running operation timed out")
    return immediate_response