import asyncio
import logging
import time

import nest_asyncio
import requests
from telegram import Bot
from telegram.request import HTTPXRequest

from config import Config, get_storage_backend, load_config
from storage import FileNotFound, StorageData
from utils import sanitize_text

ACCESS_TOKEN = "access_token"
AUTH_HEADER = "Authorization"
HTTP_STATUS_CODE = "HTTPStatusCode"
RESPONSE_METADATA = "ResponseMetadata"
TRACK = "track"
TRACKS = "tracks"
ARTISTS = "artists"
ITEMS = "items"
ADDED_BY = "added_by"
DISPLAY_NAME = "display_name"

config: Config = load_config()

spotify_playlist_url = f"https://api.spotify.com/v1/playlists/{config.spotify_playlist_id}"

MARKDOWN_V2 = "MarkdownV2"
SPOTIFY = "spotify"
NAME = "name"
ID = "id"
EXTERNAL_URLS = "external_urls"

telegram_request = HTTPXRequest(connection_pool_size=20, connect_timeout=30)
bot = Bot(token=config.bot_token, request=telegram_request)


async def send_notification(message: str, chat_id: str = config.target_chat_id, parse_mode: str = MARKDOWN_V2):
    await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)


def _make_spotify_request_headers(client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret) -> dict:
    body = {"grant_type": "client_credentials"}
    token_response = requests.post(url=config.spotify_token_url, data=body, auth=(client_id, client_secret))
    access_token = token_response.json()[ACCESS_TOKEN]
    headers = {AUTH_HEADER: f"Bearer {access_token}"}
    return headers


def get_spotify_playlist(client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret,
                         playlist_url: str = spotify_playlist_url) -> StorageData:
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)
    response = requests.get(playlist_url, headers=headers)
    response.raise_for_status()
    return response.json()


def get_spotify_user(user_id: str, client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret) -> dict:
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)
    response = requests.get(f"https://api.spotify.com/v1/users/{user_id}", headers=headers)
    response.raise_for_status()
    return response.json()


def get_playlist_tracks(playlist: dict) -> dict:
    tracks_dict = {}
    for track in playlist[TRACKS][ITEMS]:
        tracks_dict[track[TRACK][ID]] = track
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
    track_name = sanitize_text(track[TRACK][NAME])
    artists_names = [sanitize_text(artist[NAME]) for artist in track[TRACK][ARTISTS]]
    artists_names = ", ".join(artists_names)
    added_by = get_spotify_user(user_id=track[ADDED_BY][ID])
    first_name = added_by[DISPLAY_NAME].partition(' ')[0]

    return f"""*{first_name}* just added a new track 🥳

*{track_name}* 🎶  [track]({track[TRACK][EXTERNAL_URLS][SPOTIFY]})

By _{artists_names}_ 🎤

Added to the playlist: {playlist[NAME]}  [playlist]({playlist[EXTERNAL_URLS][SPOTIFY]})
"""


async def main():
    storage_backend = get_storage_backend()
    spotify_playlist = get_spotify_playlist()
    logging.info(f"Spotify playlist: {spotify_playlist[NAME]} with ID: {spotify_playlist[ID]}")

    playlist_file_key = f"{spotify_playlist[NAME]}.json"
    try:
        stored_playlist: StorageData = storage_backend.get_file(playlist_file_key)
    except FileNotFound:
        logging.warning(f"Playlist file does not exist in the storage with key: {playlist_file_key}"
                        f"If this is the first run, this is expected. Otherwise, check the storage backend."
                        f"Trying now to store the current playlist...")
        stored_playlist = storage_backend.put_file(key=playlist_file_key, data=spotify_playlist)

    logging.info(f"Stored playlist: {stored_playlist[NAME]} with ID: {stored_playlist[ID]}")

    new_tracks = compare_playlists_diff(stored_playlist=stored_playlist, current_playlist=spotify_playlist)
    notification_tasks = []
    logging.info(f"Update the stored playlist with the current playlist...")
    storage_backend.put_file(key=playlist_file_key, data=spotify_playlist)

    if not new_tracks:
        logging.info("No new tracks have been added to the playlist in the last cycle!")
        return notification_tasks

    for new_track in new_tracks:
        logging.info(f"Playlist has been updated with a new track: {new_track[TRACK][NAME]} - Sending a chat message...")
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
        time.sleep(60)
