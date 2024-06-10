import gspread
import tweepy
from google.oauth2.service_account import Credentials
import datetime
import requests
import os

print("Starting script")

# Set up Google Sheets and Drive credentials
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_file("google-service.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Social Scheduler").sheet1


def setup_api(model_name):
    # Set up API credentials based on the model
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
        if "drive.google.com/file/d/" in image_url:
            file_id = image_url.split("/")[-2]
            download_url = f"https://drive.google.com/uc?id={file_id}"
            response = requests.get(download_url)
        else:
            response = requests.get(image_url)

        response.raise_for_status()  # Raise an error if the request failed
        image_path = f"/tmp/temp_image_{len(image_paths)}.jpg"
        with open(image_path, "wb") as f:
            f.write(response.content)
        image_paths.append(image_path)
    return image_paths


def upload_media(image_paths, api):
    media_ids = []
    for image_path in image_paths:
        media = api.media_upload(image_path)
        media_ids.append(media.media_id_string)
    print("Media IDs:", media_ids)
    return media_ids


def post_to_x(client, caption, media_ids):
    response = client.create_tweet(text=caption, media_ids=media_ids)
    return response


def get_scheduled_posts():
    records = sheet.get_all_records()
    scheduled_posts = []
    for record in records:
        if record["status"] == "Scheduled" and record["platform"] == "X":
            scheduled_posts.append(record)
    return scheduled_posts


def process_posts(request):
    posts = get_scheduled_posts()
    status_column_name = "status"
    header = sheet.row_values(1)
    status_column_index = header.index(status_column_name) + 1

    for post in posts:
        post_date = datetime.datetime.strptime(post["schedule"], "%Y-%m-%d %H:%M:%S")
        if post_date <= datetime.datetime.now():
            model_name = post["model"]
            api, client = setup_api(model_name)
            image_urls = post["source"].split(",")
            image_paths = download_images(image_urls)
            media_ids = upload_media(image_paths, api)
            if media_ids:
                response = post_to_x(client, post["description"], media_ids)
                if response:
                    cell = sheet.find(post["id"])
                    sheet.update_cell(cell.row, status_column_index, "Posted")
    return "Posts processed successfully"


def main(request):
    return process_posts(request)


if __name__ == "__main__":
    main(None)
