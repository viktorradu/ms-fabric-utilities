from azure.identity import DefaultAzureCredential

class PowerBIAuth:
    def __init__(self):
        self.token = None

    def get_access_token(self):
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

        token_response = auth.get_token("https://analysis.windows.net/powerbi/api/.default")
        return token_response.token

    def get_api_auth_headers(self):
        if self.token is None:
            self.token = self.get_access_token()
        return {
                "Authorization":"Bearer " + self.token,
                "Content-Type": "application/json"
                }
        