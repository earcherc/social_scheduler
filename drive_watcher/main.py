from googleapiclient.discovery import build
from google.cloud import secretmanager
from google.oauth2 import service_account
from google.auth import default
import json


def log_message(message):
    print(message)


def get_credentials():
    log_message("Fetching credentials.")
    _, project = default()
    client = secretmanager.SecretManagerServiceClient()
    secret_name = "service-account-appspot-credentials"  # Adjust the name as per your configuration
    secret_version = "latest"
    name = f"projects/{project}/secrets/{secret_name}/versions/{secret_version}"
    response = client.access_secret_version(request={"name": name})
    creds_info = json.loads(response.payload.data.decode("UTF-8"))
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    log_message("Credentials fetched successfully.")
    return creds


def create_channel(folder_id):
    body = {
        "id": "drive-watcher",
        "type": "web_hook",
        "address": "https://us-west2-social-media-425919.cloudfunctions.net/drive_watcher",  # Your Cloud Function URL
        "payload": True,  # Indicates that notification payloads will be included in the requests
    }
    response = service.files().watch(fileId=folder_id, body=body).execute()
    print("Channel created:", response)
    return response


# Example usage, ensure to replace 'YOUR_FOLDER_ID' with the actual folder ID
if __name__ == "__main__":
    folder_id = "1B6cy-9FXJn0-Q1R8A7gx6k9dZ_Ib95hj"
    credentials = get_credentials()
    service = build("drive", "v3", credentials=credentials)
    create_channel(folder_id)
