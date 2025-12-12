# Microsoft Fabric & Power BI Utilities

A collection of Python utilities for working with Microsoft Fabric, Power BI, and Power Platform services.

## Scripts

### activity-log.py

Exports Power BI activity logs for a specified date range. The script authenticates using Azure Default Credential and retrieves activity events from the Power BI API. Features include:
- Configurable date range for log export
- Multiple partition strategies (single file, daily files, or batch files)
- Automatic batching for large time ranges
- CSV export functionality

**Configuration:**
- `input_result_folder`: Output directory for exported logs
- `input_partition_strategy`: How to split the exported files (SingleFile, DailyFiles, or BatchFiles)
- `input_batch_minutes`: Size of each batch in minutes
- `input_log_start_date` and `input_log_end_date`: Date range to export

### fabric-connection-create-serviceprincipal.py

Creates a Microsoft Fabric connection using Service Principal authentication through an on-premises data gateway. The script:
- Retrieves the gateway's public key
- Encrypts service principal credentials
- Creates a SQL data source connection with service principal authentication

**Configuration:** Requires `labconfig.py` with:
- `gatewayId`: The ID of the gateway
- `tenantId`: Azure AD tenant ID
- `servicePrincipalId`: Service principal client ID
- `servicePrincipalSecret`: Service principal secret

### fabric-dataflow-create.py

Creates a Fabric Gen2 Dataflow with a pre-configured query connecting to Databricks. The script:
- Defines query metadata and connection settings
- Creates a dataflow using Power Query M code
- Handles long-running operations (LRO) for dataflow creation

**Configuration:** Requires `labconfig.py` with:
- `workspaceId`: Target workspace ID
- `gatewayId`: Gateway ID for the connection
- `databricksHost`: Databricks host URL
- `databricksHttpPath`: Databricks HTTP path
- `databricksConnectionId`: Connection ID for Databricks

### powerbi-assign-personal-workspace.py

Assigns Power BI workspaces to specific capacity using the Admin API. The script:
- Authenticates using service principal credentials
- Calls the capacity assignment API
- Useful for bulk workspace migrations

**Configuration:** Requires `labconfig.py` with:
- `ta_tenantID`: Tenant ID
- `ta_clientID`: Client ID for authentication
- `ta_clientSecret`: Client secret

### powerbi-connection-set-oauth2-credentials.py

Sets OAuth2 credentials for a Power BI gateway data source. The script:
- Retrieves the gateway's public key
- Encrypts the OAuth2 token
- Updates the data source credentials

**Configuration:**
- `input_gateway_id`: Gateway ID
- `input_datasource_id`: Data source ID
- `input_token`: OAuth2 access token

### powerbi-connection-set-windows-credentials.py

Sets Windows authentication credentials for a Power BI gateway data source. The script:
- Retrieves the gateway's public key
- Encrypts username and password
- Updates the data source with Windows credentials

**Configuration:**
- `input_gateway_id`: Gateway ID
- `input_datasource_id`: Data source ID
- `input_username`: Windows username
- `input_password`: Windows password

### powerbi-desktop-parameter-edit.py

Modifies Power BI Desktop project parameters in PBIP format. The script:
- Creates a staging copy of the project
- Updates parameter values in the model.bim file
- Useful for automating parameter changes in CI/CD pipelines

**Configuration:**
- `parameters`: Dictionary of parameter names and their new values
- `project`: Path to the .pbip project file

### powerbi-get-organizations-shared-apps.py

Exports all Power BI apps and their users from an organization. The script:
- Retrieves all apps using the Admin API with pagination
- For each app, gets the list of users with access
- Exports data to a CSV file

**Output:** Creates `apps.csv` with app details and user access information.

### powerbi-project-rename-pages.py

Renames page folders in a Power BI project (PBIP format) to match their display names. The script:
- Takes a Power BI Report folder path as an argument
- Reads page display names from page.json files
- Creates safe folder names (removes invalid characters, limits length to 42 characters)
- Renames folders and updates all references in pages.json and page.json files
- Creates a backup archive before making changes

**Usage:**
```powershell
python powerbi-project-rename-pages.py "C:\path\to\project.Report"
```

**Features:**
- Handles duplicate names by adding numeric suffixes
- Removes invalid characters from page folder names

### powerbi-template-edit.py

Modifies Power BI template (.pbit) files by unpacking, editing, and repacking them. The script:
- Opens a .pbit file (which is a ZIP archive)
- Allows modification of internal files
- Creates a new template with the changes

**Configuration:**
- `file_in`: Input template file name

### powerplatform-get-gateways.py

Retrieves and exports all Power Platform gateways to a CSV file. The script:
- Fetches all gateway clusters with member gateways
- Exports gateway details to CSV format

**Output:** Creates `gateways.csv` with detailed gateway information.

## Library Files used by some scripts (lib/)

### authenticatedencryption.py

Implements authenticated encryption compatible with Power BI's credential encryption. Based on the C# implementation from Microsoft's PowerBI-CSharp SDK.

### encryption.py

Provides RSA-OAEP encryption functionality for encrypting credentials before sending them to Power BI/Fabric APIs.

### LRO.py

Handles Long-Running Operations (LRO) for Fabric API calls that are asynchronous.

### powerbiAuth.py

Provides authentication helpers for Power BI API calls, supporting both Azure Default Credential and Service Principal authentication.
