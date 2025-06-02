import asyncio
import random
import time
from typing import Any

import nest_asyncio
import requests
from requests.exceptions import HTTPError
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

current_offset = default_offset
send_notification_flag = True

config: Config = load_config()

telegram_request = HTTPXRequest(connection_pool_size=20, connect_timeout=30)
bot = Bot(token=config.bot_token, request=telegram_request)


async def send_notification(message: str, chat_id: str = config.target_chat_id, parse_mode: str = MARKDOWN_V2, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)
            # Add a small random delay between messages to prevent rate limiting
            await asyncio.sleep(random.uniform(5, 10))
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
    max_retries: int = 3,
) -> Any | None:
    playlist_tracks_url = _make_spotify_playlist_tracks_url(playlist_id, offset, limit)
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)

    for attempt in range(max_retries):
        try:
            playlist_tracks_response = requests.get(playlist_tracks_url, headers=headers)
            playlist_tracks_response.raise_for_status()
            return playlist_tracks_response.json()
        except HTTPError as e:
            if e.response.status_code == 429:
                # Extract retry-after header or use default backoff
                retry_after = int(e.response.headers.get("Retry-After", 1 + attempt * 2))
                logger.warning(f"Rate limited by Spotify API. Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}")
                time.sleep(retry_after)
                if attempt == max_retries - 1:
                    raise
                return None
            else:
                # Re-raise for any other HTTP errors
                raise
        except Exception as e:
            logger.error(f"Error fetching playlist tracks: {str(e)}")
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                sleep_time = (2**attempt) + random.uniform(0, 1)
                logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                return None
            else:
                raise
    return None


def get_spotify_playlist(
    client_id: str = config.spotify_client_id,
    client_secret: str = config.spotify_client_secret,
    playlist_id: str = config.spotify_playlist_id,
    max_retries: int = 3,
) -> StorageData:
    playlist = {}
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)
    playlist_url = _make_spotify_playlist_url(playlist_id)

    for attempt in range(max_retries):
        try:
            playlist_response = requests.get(playlist_url, headers=headers)
            playlist_response.raise_for_status()
            playlist = playlist_response.json()
            break
        except HTTPError as e:
            if e.response.status_code == 429:
                # Extract retry-after header or use default backoff
                retry_after = int(e.response.headers.get("Retry-After", 1 + attempt * 2))
                logger.warning(f"Rate limited by Spotify API. Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}")
                time.sleep(retry_after)
                if attempt == max_retries - 1:
                    raise
            else:
                # Re-raise for any other HTTP errors
                raise
        except Exception as e:
            logger.error(f"Error fetching playlist info: {str(e)}")
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                sleep_time = (2**attempt) + random.uniform(0, 1)
                logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            else:
                raise

    playlist_tracks_items = []
    global current_offset
    global send_notification_flag

    try:
        playlist_tracks = get_spotify_playlist_tracks(client_id, client_secret, playlist_id, current_offset, default_limit, max_retries)
        playlist_tracks_items.extend(playlist_tracks[ITEMS])
        if playlist_tracks[NEXT]:
            logger.info(
                f"Tracks up to the limit have been fetched from Spotify playlist: {playlist[NAME]} - Assuming we are recovering the playlist..."
            )
            current_offset += default_limit
            logger.info(f"Offset is set to {current_offset} for the next request")

            logger.info(f"Disabling notifications for the current cycle as we are recovering the playlist...")
            send_notification_flag = False
        else:
            if current_offset % default_limit == 0:
                logger.info(
                    f"Still in the middle of fetching tracks from Spotify playlist: {playlist[NAME]} - " f"Keep the notifications disabled"
                )
                send_notification_flag = False
            else:
                logger.debug(
                    f"All tracks have been fetched from Spotify playlist: {playlist[NAME]} - "
                    f"Enabling notifications for the current cycle..."
                )
                send_notification_flag = True

            logger.info(f"Setting the offset for the next request to {playlist_tracks[TOTAL]}")
            current_offset = playlist_tracks[TOTAL]

        logger.info(f"Fetched {len(playlist_tracks_items)} tracks from Spotify playlist: {playlist[NAME]}")
        playlist[TRACKS] = {ITEMS: playlist_tracks_items}
        return playlist
    except Exception as e:
        logger.error(f"Error while fetching tracks at offset {current_offset}: {str(e)}")
        raise


def get_spotify_user(
    user_id: str, client_id: str = config.spotify_client_id, client_secret: str = config.spotify_client_secret, max_retries: int = 3
) -> Any | None:
    headers = _make_spotify_request_headers(client_id=client_id, client_secret=client_secret)

    for attempt in range(max_retries):
        try:
            response = requests.get(f"{SPOTIFY_API_USERS_URL}/{user_id}", headers=headers)
            response.raise_for_status()
            return response.json()
        except HTTPError as e:
            if e.response.status_code == 429:
                # Extract retry-after header or use default backoff
                retry_after = int(e.response.headers.get("Retry-After", 1 + attempt * 2))
                logger.warning(f"Rate limited by Spotify API. Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}")
                time.sleep(retry_after)
                if attempt == max_retries - 1:
                    raise
                return None
            else:
                # Re-raise for any other HTTP errors
                raise
        except Exception as e:
            logger.error(f"Error fetching user info: {str(e)}")
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                sleep_time = (2**attempt) + random.uniform(0, 1)
                logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                return None
            else:
                raise
    return None


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
            if send_notification_flag:
                await send_notification(message=make_chat_message(track=new_track, playlist=spotify_playlist))
                # Sleep not to overwhelm the Telegram API
                sleep_interval = random.randint(1, 10)
                logger.info(f"Sleeping for {sleep_interval} seconds before sending the next notification...")
                await asyncio.sleep(sleep_interval)
            else:
                logger.info(f"Looks like we are recovering the Spotify playlist: {spotify_playlist[NAME]}")
                logger.info(f"Skipping sending a chat message for track {new_track[TRACK][NAME]}")
        except Exception as exception:
            logger.error(f"Failed to send notification for track {new_track[TRACK][NAME]}: {str(exception)}")
            # Continue with other notifications even if one fails
            continue

    return []


if __name__ == "__main__":
    # Always make sure we sleep before the next attempt
    try:
        check_interval = int(config.check_interval)
    except ValueError:
        check_interval = 3600
        logger.warning(f"Invalid check interval value: {config.check_interval}. Using the default value of {check_interval} seconds.")

    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    while True:
        try:
            loop.run_until_complete(main())
            logger.info(f"Sleeping for {check_interval} seconds before the next check...")
            time.sleep(check_interval)
        except Exception as e:
            logger.error(f"Error in main execution loop: {str(e)}")
            logger.exception("Main loop exception details:")
