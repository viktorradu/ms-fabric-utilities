from azure.identity import DefaultAzureCredential
import os

class PowerBIAuth:
    def __init__(self, tenant_id=None, client_id=None, client_secret=None):
        self.token = None
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        if tenant_id and client_id and client_secret:
            os.environ['AZURE_TENANT_ID'] = tenant_id
            os.environ['AZURE_CLIENT_ID'] = client_id
            os.environ['AZURE_CLIENT_SECRET'] = client_secret

    def get_access_token(self):
        auth = DefaultAzureCredential(
            exclude_interactive_browser_credential=False,
            exclude_managed_identity_credential = True,
            exclude_environment_credential = self.tenant_id is None or self.client_id is None or self.client_secret is None,
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
        