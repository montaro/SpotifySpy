import asyncio
import random
import time

import nest_asyncio
import requests
from telegram import Bot
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.request import HTTPXRequest

from config import Config, get_storage_backend, load_config
from storage import FileNotFound, StorageData
from utils import get_logger, sanitize_text


logger = get_logger()

ACCESS_TOKEN = "access_token"
AUTH_HEADER = "Authorization"
HTTP_STATUS_CODE = "HTTPStatusCode"
RESPONSE_METADATA = "ResponseMetadata"
TRACK = "track"
TRACKS = "tracks"
ARTISTS = "artists"
ITEMS = "items"
NEXT = "next"
TOTAL = "total"
OFFSET = "offset"
LIMIT = "limit"
ADDED_BY = "added_by"
DISPLAY_NAME = "display_name"
MARKDOWN_V2 = "MarkdownV2"
SPOTIFY = "spotify"
NAME = "name"
ID = "id"
EXTERNAL_URLS = "external_urls"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
SPOTIFY_API_PLAYLISTS_URL = f"{SPOTIFY_API_BASE_URL}/playlists"
SPOTIFY_API_USERS_URL = f"{SPOTIFY_API_BASE_URL}/users"

default_limit = 100
default_offset = 0

config: Config = load_config()

telegram_request = HTTPXRequest(connection_pool_size=20, connect_timeout=30)
bot = Bot(token=config.bot_token, request=telegram_request)


async def send_notification(message: str, chat_id: str = config.target_chat_id, parse_mode: str = MARKDOWN_V2, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)
            # Add a small random delay between messages to prevent rate limiting
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return
        except TimedOut:
            logger.warning(f"Telegram API timeout on attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)  # Exponential backoff
            else:
                logger.error("Failed to send notification after all retries")
                raise
        except RetryAfter as e:
            logger.warning(f"Rate limited by Telegram API. Waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after)
        except NetworkError as e:
            logger.warning(f"Network error on attempt {attempt + 1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
            else:
                logger.error("Failed to send notification after all retries")
                raise
        except Exception as e:
            logger.error(f"Unexpected error sending notification: {str(e)}")
            raise


def _make_spotify_playlist_url(playlist_id: str = config.spotify_playlist_id) -> str:
    fields = "id,name,external_urls"
    return f"{SPOTIFY_API_PLAYLISTS_URL}/{playlist_id}?fields={fields}"


def _make_spotify_playlist_tracks_url(
    playlist_id: str = config.spotify_playlist_id, offset: int = default_offset, limit: int = default_limit
) -> str:
    fields = "limit,total,offset,next,items(added_by.id,track(id,name,external_urls,artists(name)))"
    return f"{SPOTIFY_API_PLAYLISTS_URL}/{playlist_id}/tracks?fields={fields}&offset={offset}&limit={limit}"


def _make_spotify_request_headers(client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret) -> dict:
    body = {"grant_type": "client_credentials"}
    token_response = requests.post(url=config.spotify_token_url, data=body, auth=(client_id, client_secret))
    access_token = token_response.json()[ACCESS_TOKEN]
    headers = {AUTH_HEADER: f"Bearer {access_token}"}
    return headers


def get_spotify_playlist_tracks(
    client_id: str = config.spotify_client_id,
    client_secret: str = config.spotify_client_secret,
    playlist_id: str = config.spotify_playlist_id,
    offset: int = default_offset,
    limit: int = default_limit,
) -> dict:
    playlist_tracks_url = _make_spotify_playlist_tracks_url(playlist_id, offset, limit)
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)
    playlist_tracks_response = requests.get(playlist_tracks_url, headers=headers)
    playlist_tracks_response.raise_for_status()
    return playlist_tracks_response.json()


def get_spotify_playlist(
    client_id: str = config.spotify_client_id,
    client_secret: str = config.spotify_client_secret,
    playlist_id: str = config.spotify_playlist_id,
) -> StorageData:
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)
    playlist_url = _make_spotify_playlist_url(playlist_id)
    playlist_response = requests.get(playlist_url, headers=headers)
    playlist_response.raise_for_status()
    playlist = playlist_response.json()

    playlist_tracks_items = []

    offset = default_offset
    limit = default_limit

    while True:
        playlist_tracks = get_spotify_playlist_tracks(client_id, client_secret, playlist_id, offset, limit)
        playlist_tracks_items.extend(playlist_tracks[ITEMS])
        if not playlist_tracks[NEXT]:
            break
        else:
            offset = playlist_tracks[OFFSET] + default_limit

    playlist[TRACKS] = {ITEMS: playlist_tracks_items}
    return playlist


def get_spotify_user(user_id: str, client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret) -> dict:
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)
    response = requests.get(f"{SPOTIFY_API_USERS_URL}/{user_id}", headers=headers)
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
    first_name = added_by[DISPLAY_NAME].partition(" ")[0]

    return f"""*{first_name}* just added a new track 🥳

*{track_name}* 🎶  [track]({track[TRACK][EXTERNAL_URLS][SPOTIFY]})

By _{artists_names}_ 🎤

Added to the playlist: {playlist[NAME]}  [playlist]({playlist[EXTERNAL_URLS][SPOTIFY]})
"""


async def main():
    storage_backend = get_storage_backend()
    spotify_playlist = get_spotify_playlist()
    logger.info(f"Spotify playlist: {spotify_playlist[NAME]} with ID: {spotify_playlist[ID]}")

    playlist_file_key = f"{spotify_playlist[NAME]}.json"
    try:
        stored_playlist: StorageData = storage_backend.get_file(playlist_file_key)
    except FileNotFound:
        logger.warning(
            f"Playlist file does not exist in the storage with name: {playlist_file_key}\n"
            f"If this is the first run, this is expected. Otherwise, check the storage backend.\n"
            f"Trying now to store the current playlist..."
        )
        stored_playlist = storage_backend.put_file(key=playlist_file_key, data=spotify_playlist)

    logger.info(f"Stored playlist: {stored_playlist[NAME]} with ID: {stored_playlist[ID]}")

    new_tracks = compare_playlists_diff(stored_playlist=stored_playlist, current_playlist=spotify_playlist)
    logger.info("Update the stored playlist with the current playlist...")
    storage_backend.put_file(key=playlist_file_key, data=spotify_playlist)

    if not new_tracks:
        logger.info("No new tracks have been added to the playlist in the last cycle!")
        return []

    # Process notifications sequentially to avoid overwhelming the API
    for new_track in new_tracks:
        try:
            logger.info(f"Playlist has been updated with a new track: {new_track[TRACK][NAME]} - Sending a chat message...")
            await send_notification(message=make_chat_message(track=new_track, playlist=spotify_playlist))
        except Exception as e:
            logger.error(f"Failed to send notification for track {new_track[TRACK][NAME]}: {str(e)}")
            # Continue with other notifications even if one fails
            continue

    return []


if __name__ == "__main__":
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    while True:
        tasks = loop.run_until_complete(main())
        for task in asyncio.as_completed(tasks):
            loop.run_until_complete(task)
        try:
            check_interval = int(config.check_interval)
        except ValueError:
            check_interval = 60
            logger.warning(f"Invalid check interval value: {config.check_interval}. Using the default value of {check_interval} seconds.")
        logger.info(f"Sleeping for {check_interval} seconds...\n\n")
        time.sleep(check_interval)
