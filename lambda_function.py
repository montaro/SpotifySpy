import asyncio
import io
import json
import logging
import os
import time

from dotenv import load_dotenv

import boto3
import requests
from telegram import Bot
import nest_asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

load_dotenv()

SPOTIFY_TOKEN_URL = os.getenv('SPOTIFY_TOKEN_URL', "")
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', "")
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', "")
SPOTIFY_PLAYLIST_ID = os.getenv('SPOTIFY_PLAYLIST_ID', "")
BOT_TOKEN = os.getenv('BOT_TOKEN', "")
playlist_bucket = os.getenv('BUCKET', "")
target_chat_id = os.getenv('TARGET_CHAT_ID', "")
spotify_playlist_url = f"https://api.spotify.com/v1/playlists/{SPOTIFY_PLAYLIST_ID}"

MARKDOWN_V2 = "MarkdownV2"
S3 = "s3"
SPOTIFY = "spotify"
NAME = "name"
ID = "id"
EXTERNAL_URLS = "external_urls"

# BOT_TOKEN = "5992712569:AAH0so-PzMHLFfN1pil9fGEu0dmKhMm9VJY"
# SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
# SPOTIFY_CLIENT_ID = "70a5a5dff64f4f2c945bcb04f84e73c4"
# SPOTIFY_CLIENT_SECRET = "9f10d6e242604d8c87acff5ad4504619"
# SPOTIFY_PLAYLIST_ID = "4c4hQyGXLKzdKJIg6mvtPP"

# bucket = "spotify-playlist-telegram"
# target_chat_id = "-4283567220"  # Chat ID of the channel "Ahmed-Spotify-Playlist-Updates"

bot = Bot(token=BOT_TOKEN)
s3_client = boto3.client(S3)


async def send_notification(message: str, chat_id: str = target_chat_id, parse_mode: str = MARKDOWN_V2):
    await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)


def get_spotify_playlist(client_id: str = SPOTIFY_CLIENT_ID, client_secret: str = SPOTIFY_CLIENT_SECRET,
                         playlist_url: str = spotify_playlist_url) -> dict:
    body = {"grant_type": "client_credentials"}
    token_response = requests.post(url=SPOTIFY_TOKEN_URL, data=body, auth=(client_id, client_secret))
    access_token = token_response.json()['access_token']
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(playlist_url, headers=headers)
    response.raise_for_status()
    return response.json()


def store_playlist(key: str, playlist_dict: dict, bucket: str = playlist_bucket) -> dict:
    logging.info(f"Storing playlist named {playlist_dict[NAME]} in S3 bucket: {bucket} with key: {key}")
    try:
        file_like_object = io.StringIO()
        json.dump(obj=playlist_dict, fp=file_like_object)
        file_like_object.seek(0)
        response = s3_client.put_object(Body=file_like_object.getvalue().encode(), Bucket=bucket, Key=key)
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            logging.info(
                f"Playlist named {playlist_dict[NAME]} stored successfully in S3 bucket: {bucket} with key: {key}")
        else:
            logging.error(
                f"Failed to store playlist in S3 with status code: {response['ResponseMetadata']['HTTPStatusCode']}"
                f" and response: {response}")
        return response
    except Exception as e:
        logging.error(e)
        raise e


def get_stored_playlist(key: str, bucket: str = playlist_bucket) -> dict:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except s3_client.exceptions.NoSuchKey:
        logging.info(f"Playlist file does not exist in the bucket: {bucket} with key: {key}")
        return {}

    stored_playlist = json.load(response['Body'])
    logging.info(f"Retrieved playlist named {stored_playlist[NAME]} from S3 bucket: {bucket} with key: {key}")
    return stored_playlist


def get_playlist_tracks(playlist: dict) -> dict:
    tracks_dict = {}
    for track in playlist['tracks']['items']:
        tracks_dict[track['track'][ID]] = track['track']
    return tracks_dict


def compare_playlists_diff(stored_playlist: dict, current_playlist: dict) -> list[dict]:
    stored_playlist_tracks = get_playlist_tracks(stored_playlist)
    current_playlist_tracks = get_playlist_tracks(current_playlist)
    diff_tracks_ids = set(current_playlist_tracks.keys()) - set(stored_playlist_tracks.keys())
    diff_tracks = []
    while diff_tracks_ids:
        track_id = diff_tracks_ids.pop()
        diff_tracks.append(current_playlist_tracks[track_id])
    return diff_tracks


def make_chat_message(track: dict, playlist: dict) -> str:
    track_name = track[NAME]
    track_name = track_name.replace("-", "").replace("(", "").replace(")", "")
    artists_names = [artist[NAME] for artist in track["artists"]]
    artists_names = ", ".join(artists_names).replace("-", "")

    return f"""New track 🥳

*{track_name}* 🎶  [track]({track[EXTERNAL_URLS][SPOTIFY]})

By _{artists_names}_ 🎤

Added to the playlist: {playlist[NAME]}  [playlist]({playlist[EXTERNAL_URLS][SPOTIFY]})
"""


def main():
    spotify_playlist = get_spotify_playlist()
    logging.info(f"Spotify playlist: {spotify_playlist[NAME]} with ID: {spotify_playlist[ID]}")

    playlist_file_key = f"{spotify_playlist[NAME]}.json"
    s3_playlist = get_stored_playlist(key=playlist_file_key)
    if not s3_playlist:
        logging.warning("Playlist file does not exist in the bucket. Storing the current playlist...")
        store_playlist(key=playlist_file_key, playlist_dict=spotify_playlist)
        s3_playlist = spotify_playlist

    logging.info(f"Stored playlist: {s3_playlist[NAME]} with ID: {s3_playlist[ID]}")

    new_tracks = compare_playlists_diff(stored_playlist=s3_playlist, current_playlist=spotify_playlist)
    logging.info(f"Update the stored playlist with the current playlist...")
    store_playlist(key=playlist_file_key, playlist_dict=spotify_playlist)
    if not new_tracks:
        logging.info("No new tracks have been added to the playlist in the last cycle!")
    while new_tracks:
        new_track = new_tracks.pop()
        logging.info(f"Playlist has been updated with a new track: {new_track[NAME]} - Sending a chat message...")
        chat_message = make_chat_message(track=new_track, playlist=spotify_playlist)
        yield send_notification(message=chat_message)


if __name__ == "__main__":
    # def lambda_handler(event, context):
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    nest_asyncio.apply()
    while True:
        coroutines = list(main())
        # loop.run_until_complete(asyncio.gather(*coroutines))
        asyncio.run(asyncio.gather(*coroutines))
        logging.info("Sleeping for 10 minutes...")
        time.sleep(600)
