import gspread
import tweepy
from google.oauth2.service_account import Credentials
import datetime
import requests
import os
import json
from google.cloud import secretmanager
import google.auth
import mimetypes


def log_message(message):
    # This function will help to standardize the logging format
    print(f"{datetime.datetime.now()}: {message}")


def initialize_sheet():
    log_message("Initializing Google Sheet access.")

    # Create the Secret Manager client.
    _, project = google.auth.default()
    client = secretmanager.SecretManagerServiceClient()
    secret_name = "social-schedule-secret"  # The name of your secret
    secret_version = "latest"  # Can be a version number or 'latest'
    name = f"projects/{project}/secrets/{secret_name}/versions/{secret_version}"

    # Access the secret version.
    response = client.access_secret_version(request={"name": name})
    secret_string = response.payload.data.decode("UTF-8")

    # Parse the JSON string back into a dictionary.
    creds_info = json.loads(secret_string)

    # Use the parsed JSON dictionary to create credentials.
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    # Authorize with gspread using these credentials.
    client = gspread.authorize(creds)
    log_message("Google Sheet access initialized successfully.")
    return client.open("Social Scheduler").sheet1


def setup_api(model_name):
    log_message(f"Setting up API for model: {model_name}")
    bearer_token = os.getenv(f"{model_name.upper()}_BEARER_TOKEN")
    access_token = os.getenv(f"{model_name.upper()}_ACCESS_TOKEN")
    access_token_secret = os.getenv(f"{model_name.upper()}_ACCESS_TOKEN_SECRET")
    api_key = os.getenv(f"{model_name.upper()}_API_KEY")
    api_key_secret = os.getenv(f"{model_name.upper()}_API_KEY_SECRET")

    auth = tweepy.OAuthHandler(consumer_key=api_key, consumer_secret=api_key_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth, wait_on_rate_limit=True)
    client = tweepy.Client(
        bearer_token=bearer_token,
        access_token=access_token,
        access_token_secret=access_token_secret,
        consumer_key=api_key,
        consumer_secret=api_key_secret,
        wait_on_rate_limit=True,
    )
    log_message(f"API setup completed for model: {model_name}")
    return api, client


def download_images(image_urls):
    log_message("Starting to download images.")
    image_paths = []
    for image_url in image_urls:
        try:
            if "drive.google.com/file/d/" in image_url:
                log_message(f"Downloading image from Google Drive: {image_url}")
                file_id = image_url.split("/")[-2]
                download_url = f"https://drive.google.com/uc?id={file_id}"
                response = requests.get(download_url, timeout=30)
            else:
                log_message(f"Downloading image from URL: {image_url}")
                response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image_path = f"/tmp/temp_image_{len(image_paths)}.jpg"
            with open(image_path, "wb") as f:
                f.write(response.content)
            image_paths.append(image_path)
            log_message(f"Image downloaded successfully: {image_path}")
        except requests.RequestException as e:
            log_message(f"Failed to download image: {e}")
            return None, str(e)
    log_message("Image download process completed.")
    return image_paths, None


def upload_media(image_paths, api):
    log_message("Starting to upload media.")
    media_ids = []
    if not image_paths:  # If no images were downloaded successfully
        log_message("No images to upload.")
        return media_ids, None  # Return empty list of media_ids without error
    try:
        for image_path in image_paths:
            mime_type, _ = mimetypes.guess_type(image_path)
            log_message(f"Uploading media: {image_path}, MIME type: {mime_type}")

            # Upload the media using Tweepy
            media = api.media_upload(image_path)
            media_ids.append(media.media_id_string)
            log_message(f"Media uploaded successfully: {image_path}")
    except Exception as e:
        log_message(f"Error uploading media: {e}")
        return None, str(e)
    log_message("Media upload process completed.")
    return media_ids, None


def post_to_x(client, caption, media_ids, model_name):
    log_message(f"Posting to Twitter for model: {model_name}")
    try:
        # Handle both situations: with and without media_ids
        response = (
            client.create_tweet(text=caption, media_ids=media_ids)
            if media_ids
            else client.create_tweet(text=caption)
        )
        log_message(
            f"Successfully posted: Model Name='{model_name}', Caption='{caption}'"
        )
        return response, None
    except Exception as e:
        log_message(
            f"Failed to post: Model Name='{model_name}', Caption='{caption}', Error={str(e)}"
        )
        return None, str(e)


def get_scheduled_posts(sheet):
    log_message("Retrieving scheduled posts from Google Sheet.")
    records = sheet.get_all_records()
    scheduled_posts = [
        record
        for record in records
        if record["status"] == "Scheduled" and record["platform"] == "X"
    ]
    if not scheduled_posts:
        log_message("No posts scheduled to be posted.")
    else:
        log_message(f"Found {len(scheduled_posts)} scheduled posts.")
    return scheduled_posts


def process_posts(sheet):
    log_message("Starting to process posts.")
    posts = get_scheduled_posts(sheet)
    all_values = sheet.get_all_values()
    header = all_values[0]
    status_col_idx = header.index("status") + 1
    last_updated_col_idx = header.index("last_updated") + 1
    error_col_idx = header.index("error") + 1

    for post in posts:
        row_index = next(
            i
            for i, row in enumerate(all_values, start=1)
            if str(row[0]) == str(post["id"])
        )
        log_message(
            f"About to process post: Model Name='{post['model']}', Caption='{post['description']}'"
        )
        if (
            datetime.datetime.strptime(post["schedule"], "%Y-%m-%d %H:%M:%S")
            <= datetime.datetime.now()
        ):
            model_name = post["model"]
            api, client = setup_api(model_name)
            image_urls = post["source"].split(",") if post["source"] else []
            image_paths, download_error = (
                download_images(image_urls) if image_urls else ([], None)
            )
            if download_error:
                log_message(f"Error downloading images: {download_error}")
                sheet.update_cell(row_index, error_col_idx, download_error)
                continue
            media_ids, upload_error = upload_media(image_paths, api)
            if upload_error:
                log_message(f"Error uploading media: {upload_error}")
                sheet.update_cell(row_index, error_col_idx, upload_error)
                continue
            response, post_error = post_to_x(
                client, post["description"], media_ids, model_name
            )
            if post_error:
                log_message(f"Error posting to X: {post_error}")
                sheet.update_cell(row_index, error_col_idx, post_error)
                continue
            sheet.update_cell(row_index, status_col_idx, "Posted")
            sheet.update_cell(
                row_index, last_updated_col_idx, str(datetime.datetime.now())
            )
            log_message(f"Post processed successfully: {post['id']}")


def main(request):
    log_message("Starting main process.")
    sheet = initialize_sheet()
    process_posts(sheet)
    log_message("Main process completed.")
    return "Process completed"


if __name__ == "__main__":
    main()
