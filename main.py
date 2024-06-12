import gspread
import tweepy
from google.oauth2.service_account import Credentials
import datetime
import requests
import os
import json
from google.cloud import secretmanager
import google.auth


def initialize_sheet():
    # Create the Secret Manager client.
    _, project = google.auth.default()
    client = secretmanager.SecretManagerServiceClient()
    secret_name = "service-account-appspot-credentials"  # The name of your secret
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
    return client.open("Social Scheduler").sheet1


def setup_api(model_name):
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
    return api, client


def download_images(image_urls):
    image_paths = []
    for image_url in image_urls:
        try:
            if "drive.google.com/file/d/" in image_url:
                file_id = image_url.split("/")[-2]
                download_url = f"https://drive.google.com/uc?id={file_id}"
                response = requests.get(download_url, timeout=30)
            else:
                response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image_path = f"/tmp/temp_image_{len(image_paths)}.jpg"
            with open(image_path, "wb") as f:
                f.write(response.content)
            image_paths.append(image_path)
        except requests.RequestException as e:
            print(f"Failed to download image: {e}")
            return None, str(e)
    return image_paths, None


def upload_media(image_paths, api):
    media_ids = []
    if not image_paths:  # If no images were downloaded successfully
        return media_ids, None  # Return empty list of media_ids without error
    try:
        for image_path in image_paths:
            media = api.media_upload(image_path)
            media_ids.append(media.media_id_string)
    except Exception as e:
        print(f"Error uploading media: {e}")
        return None, str(e)
    return media_ids, None


def post_to_x(client, caption, media_ids, model_name):
    try:
        # Handle both situations: with and without media_ids
        response = (
            client.create_tweet(text=caption, media_ids=media_ids)
            if media_ids
            else client.create_tweet(text=caption)
        )
        print(f"Successfully posted: Model Name='{model_name}', Caption='{caption}'")
        return response, None
    except Exception as e:
        print(
            f"Failed to post: Model Name='{model_name}', Caption='{caption}', Error={str(e)}"
        )
        return None, str(e)


def get_scheduled_posts(sheet):
    records = sheet.get_all_records()
    scheduled_posts = [
        record
        for record in records
        if record["status"] == "Scheduled" and record["platform"] == "X"
    ]
    if not scheduled_posts:
        print("No posts scheduled to be posted.")
    else:
        print(f"Found {len(scheduled_posts)} scheduled posts.")
    return scheduled_posts


def process_posts(sheet):
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
        print(
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
                sheet.update_cell(row_index, error_col_idx, download_error)
                continue
            media_ids, upload_error = upload_media(image_paths, api)
            if upload_error:
                sheet.update_cell(row_index, error_col_idx, upload_error)
                continue
            response, post_error = post_to_x(
                client, post["description"], media_ids, model_name
            )
            if post_error:
                sheet.update_cell(row_index, error_col_idx, post_error)
                continue
            sheet.update_cell(row_index, status_col_idx, "Posted")
            sheet.update_cell(
                row_index, last_updated_col_idx, str(datetime.datetime.now())
            )


def main(request):
    sheet = initialize_sheet()
    process_posts(sheet)
    return "Process completed"


if __name__ == "__main__":
    main()
