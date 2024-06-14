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
    secret_name = "service-account-appspot-credentials"
    secret_version = "latest"
    name = f"projects/{project}/secrets/{secret_name}/versions/{secret_version}"
    response = client.access_secret_version(request={"name": name})
    creds_info = json.loads(response.payload.data.decode("UTF-8"))
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    log_message("Credentials fetched successfully.")
    return creds


def create_channel(folder_id, credentials):
    service = build("drive", "v3", credentials=credentials)
    body = {
        "id": "drive-watcher",
        "type": "web_hook",
        "address": "https://us-west2-social-media-425919.cloudfunctions.net/drive_watcher",
        "payload": True,
    }
    response = service.files().watch(fileId=folder_id, body=body).execute()
    print("Channel created:", response)
    return response


def main(request):
    folder_id = "1B6cy-9FXJn0-Q1R8A7gx6k9dZ_Ib95hj"
    credentials = get_credentials()
    create_channel(folder_id, credentials)
    return "Channel Created Successfully", 200


if __name__ == "__main__":
    main()
