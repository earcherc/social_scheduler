import gspread
import tweepy
from google.oauth2.service_account import Credentials
import datetime
import requests
import os


def initialize_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file("google-service.json", scopes=scope)
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
                response = requests.get(download_url)
            else:
                response = requests.get(image_url)
            response.raise_for_status()
            image_path = f"/tmp/temp_image_{len(image_paths)}.jpg"
            with open(image_path, "wb") as f:
                f.write(response.content)
            image_paths.append(image_path)
        except requests.RequestException as e:
            print(f"Failed to download image: {e}")
            return None, str(e)  # Return error message
    return image_paths, None


def upload_media(image_paths, api):
    media_ids = []
    if not image_paths:
        return None, "Download failed, no images to upload"
    try:
        for image_path in image_paths:
            media = api.media_upload(image_path)
            media_ids.append(media.media_id_string)
    except Exception as e:
        return None, str(e)
    return media_ids, None


def post_to_x(client, caption, media_ids):
    try:
        response = client.create_tweet(text=caption, media_ids=media_ids)
        return response, None
    except Exception as e:
        return None, str(e)


def get_scheduled_posts(sheet):
    records = sheet.get_all_records()
    return [
        record
        for record in records
        if record["status"] == "Scheduled" and record["platform"] == "X"
    ]


def process_posts(sheet):
    posts = get_scheduled_posts(sheet)
    header = sheet.row_values(1)
    status_col_idx = header.index("status") + 1
    last_updated_col_idx = header.index("last_updated") + 1
    error_col_idx = header.index("error") + 1

    for post in posts:
        if (
            datetime.datetime.strptime(post["schedule"], "%Y-%m-%d %H:%M:%S")
            <= datetime.datetime.now()
        ):
            model_name = post["model"]
            api, client = setup_api(model_name)
            image_urls = post["source"].split(",")
            image_paths, download_error = download_images(image_urls)
            if download_error:
                sheet.update_cell(post["row"], error_col_idx, download_error)
                continue  # Skip further processing if download fails
            media_ids, upload_error = upload_media(image_paths, api)
            if upload_error:
                sheet.update_cell(post["row"], error_col_idx, upload_error)
                continue
            response, post_error = post_to_x(client, post["description"], media_ids)
            if post_error:
                sheet.update_cell(post["row"], error_col_idx, post_error)
                continue
            sheet.update_cell(post["row"], status_col_idx, "Posted")
            sheet.update_cell(
                post["row"], last_updated_col_idx, str(datetime.datetime.now())
            )
    return "Posts processed successfully"


def main():
    sheet = initialize_sheet()
    result = process_posts(sheet)
    print(result)


if __name__ == "__main__":
    main()
