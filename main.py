import datetime
import json
import os
import requests
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import gspread
import tweepy


def log_message(message):
    print(f"{datetime.datetime.now()}: {message}")


def get_credentials():
    log_message("Fetching credentials.")
    _, project = default()
    client = secretmanager.SecretManagerServiceClient()
    secret_name = "social-schedule-secret"
    secret_version = "latest"
    name = f"projects/{project}/secrets/{secret_name}/versions/{secret_version}"
    response = client.access_secret_version(request={"name": name})
    creds_info = json.loads(response.payload.data.decode("UTF-8"))
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )
    log_message("Credentials fetched successfully.")
    return creds


def initialize_sheet(creds):
    log_message("Initializing Google Sheet access.")
    gspread_client = gspread.authorize(creds)
    log_message("Google Sheet access initialized successfully.")
    return gspread_client.open("Social Scheduler").sheet1


def setup_google_drive(creds):
    log_message("Setting up Google Drive client.")
    drive_service = build("drive", "v3", credentials=creds)
    log_message("Google Drive client setup completed.")
    return drive_service


def download_image(image_url, drive_service):
    if "drive.google.com" in image_url:
        log_message(f"Downloading image from Google Drive: {image_url}")
        file_id = image_url.split("/")[-2]
        request = drive_service.files().get_media(fileId=file_id)
        image_path = f"/tmp/temp_image_{file_id}.jpg"
        with open(image_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                log_message(f"Download {int(status.progress() * 100)}%.")
        log_message(f"Image downloaded successfully from Google Drive: {image_path}")
        return image_path
    else:
        log_message(f"Downloading image from URL: {image_url}")
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        image_path = "/tmp/temp_image.jpg"
        with open(image_path, "wb") as f:
            f.write(response.content)
        log_message(f"Image downloaded successfully: {image_path}")
        return image_path


def setup_api(model_name):
    log_message(f"Setting up API for model: {model_name}")
    consumer_key = os.getenv(f"{model_name.upper()}_API_KEY")
    consumer_secret = os.getenv(f"{model_name.upper()}_API_KEY_SECRET")
    access_token = os.getenv(f"{model_name.upper()}_ACCESS_TOKEN")
    access_token_secret = os.getenv(f"{model_name.upper()}_ACCESS_TOKEN_SECRET")
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth, wait_on_rate_limit=True)
    client = tweepy.Client(
        bearer_token=os.getenv(f"{model_name.upper()}_BEARER_TOKEN"),
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        wait_on_rate_limit=True,
    )
    log_message(f"API and Client setup completed for model: {model_name}")
    return api, client


def upload_media(image_path, api):
    log_message(f"Starting to upload media: {image_path}")
    # Upload the image using the Tweepy API object and get the media ID
    media = api.media_upload(filename=image_path)
    media_id = media.media_id_string
    log_message(f"Media uploaded successfully: {media_id}")
    return media_id


def post_to_twitter(client, caption, media_id, model_name, sheet, post_row):
    log_message(f"Posting to Twitter for model: {model_name}")
    try:
        response = client.create_tweet(text=caption, media_ids=[media_id])
        log_message(
            f"Successfully posted: Model Name='{model_name}', Caption='{caption}'"
        )
        # Update sheet to mark as posted
        sheet.update_cell(post_row, sheet.find("status").col, "Posted")
        sheet.update_cell(
            post_row, sheet.find("last_updated").col, str(datetime.datetime.now())
        )
    except Exception as e:
        log_message(f"Failed to post: {str(e)}")
        sheet.update_cell(post_row, sheet.find("error").col, str(e))


def process_posts(sheet, drive_service):
    posts = sheet.get_all_records()
    for idx, post in enumerate(posts, start=2):  # Starting from 2 because of headers
        if (
            post["status"] == "Scheduled"
            and post["platform"] == "X"
            and datetime.datetime.strptime(post["schedule"], "%Y-%m-%d %H:%M:%S")
            <= datetime.datetime.now()
        ):
            model_name = post["model"]
            api, client = setup_api(model_name)
            image_path = download_image(post["source"], drive_service)
            media_id = upload_media(image_path, api)
            post_to_twitter(
                client, post["description"], media_id, model_name, sheet, idx
            )


def main(request):
    creds = get_credentials()
    sheet = initialize_sheet(creds)
    drive_service = setup_google_drive(creds)
    process_posts(sheet, drive_service)
    return "Posts processed successfully"


if __name__ == "__main__":
    main()
