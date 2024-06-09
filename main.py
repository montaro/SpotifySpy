import asyncio
import io
import json
import logging
import time

import boto3
import nest_asyncio
import requests
from telegram import Bot

from config import Config, load_config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ACCESS_TOKEN = "access_token"
AUTH_HEADER = "Authorization"
HTTP_STATUS_CODE = "HTTPStatusCode"
RESPONSE_METADATA = "ResponseMetadata"
TRACK = "track"
TRACKS = "tracks"

config: Config = load_config()

spotify_playlist_url = f"https://api.spotify.com/v1/playlists/{config.spotify_playlist_id}"

MARKDOWN_V2 = "MarkdownV2"
S3 = "s3"
SPOTIFY = "spotify"
NAME = "name"
ID = "id"
EXTERNAL_URLS = "external_urls"

bot = Bot(token=config.bot_token)
s3_client = boto3.client(S3)


async def send_notification(message: str, chat_id: str = config.target_chat_id, parse_mode: str = MARKDOWN_V2):
    await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)


def get_spotify_playlist(client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret,
                         playlist_url: str = spotify_playlist_url) -> dict:
    body = {"grant_type": "client_credentials"}
    token_response = requests.post(url=config.spotify_token_url, data=body, auth=(client_id, client_secret))
    access_token = token_response.json()[ACCESS_TOKEN]
    headers = {AUTH_HEADER: f"Bearer {access_token}"}
    response = requests.get(playlist_url, headers=headers)
    response.raise_for_status()
    return response.json()


def store_playlist(key: str, playlist_dict: dict, bucket: str = config.bucket) -> dict:
    logging.info(f"Storing playlist named {playlist_dict[NAME]} in S3 bucket: {bucket} with key: {key}")
    try:
        file_like_object = io.StringIO()
        json.dump(obj=playlist_dict, fp=file_like_object)
        file_like_object.seek(0)
        response = s3_client.put_object(Body=file_like_object.getvalue().encode(), Bucket=bucket, Key=key)
        if response[RESPONSE_METADATA][HTTP_STATUS_CODE] == 200:
            logging.info(
                f"Playlist named {playlist_dict[NAME]} stored successfully in S3 bucket: {bucket} with key: {key}")
        else:
            logging.error(
                f"Failed to store playlist in S3 with status code: {response[RESPONSE_METADATA][HTTP_STATUS_CODE]}"
                f" and response: {response}")
        return response
    except Exception as e:
        logging.error(e)
        raise e


def get_stored_playlist(key: str, bucket: str = config.bucket) -> dict:
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
    for track in playlist[TRACKS]['items']:
        tracks_dict[track[TRACK][ID]] = track[TRACK]
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


def sanitize_text(text: str) -> str:
    return (
        text.replace(r"_", r"\_").
        replace(r"*", r"\*").
        replace(r"[", r"\[").
        replace(r"`", r"\`").
        replace(r"-", r"\-").
        replace(r"(", r"\(").
        replace(r")", r"\)")
    )


def make_chat_message(track: dict, playlist: dict) -> str:
    track_name = sanitize_text(track[NAME])
    artists_names = [sanitize_text(artist[NAME]) for artist in track["artists"]]
    artists_names = ", ".join(artists_names)

    return f"""New track 🥳

*{track_name}* 🎶  [track]({track[EXTERNAL_URLS][SPOTIFY]})

By _{artists_names}_ 🎤

Added to the playlist: {playlist[NAME]}  [playlist]({playlist[EXTERNAL_URLS][SPOTIFY]})
"""


async def main():
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
    notification_tasks = []
    logging.info(f"Update the stored playlist with the current playlist...")
    store_playlist(key=playlist_file_key, playlist_dict=spotify_playlist)

    if not new_tracks:
        logging.info("No new tracks have been added to the playlist in the last cycle!")
        return notification_tasks

    for new_track in new_tracks:
        logging.info(f"Playlist has been updated with a new track: {new_track[NAME]} - Sending a chat message...")
        notification_tasks.append(
            send_notification(message=make_chat_message(track=new_track, playlist=spotify_playlist))
        )
    return notification_tasks


if __name__ == "__main__":
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    while True:
        tasks = loop.run_until_complete(main())
        for task in asyncio.as_completed(tasks):
            loop.run_until_complete(task)
        logging.info("Sleeping for 1 minute...\n\n")
        time.sleep(20)
