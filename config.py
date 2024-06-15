import logging
import os
from dataclasses import dataclass, fields

from dotenv import load_dotenv

from storage import Storage
from storage.filesystem import FilesystemStorage
from storage.s3 import S3Storage


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

_storage_backend: Storage


@dataclass
class Config:
    spotify_token_url: str
    spotify_client_id: str
    spotify_client_secret: str
    spotify_playlist_id: str
    bot_token: str
    target_chat_id: str
    storage_backend: str
    filesystem_storage_path: str
    s3_region: str
    s3_bucket: str
    s3_access_key_id: str
    s3_secret_access_key: str


def _from_dict(dict_: dict) -> Config:
    dict_ = {k.lower(): v for k, v in dict_.items()}
    return Config(**dict_)


def set_storage_backend(config: Config) -> Storage:
    global _storage_backend
    match config.storage_backend:
        case "s3":
            _storage_backend = S3Storage(config=config)
        case "filesystem":
            _storage_backend = FilesystemStorage(config=config)
        case _:
            raise ValueError("Invalid storage backend")

    return _storage_backend


def get_storage_backend() -> Storage:
    return _storage_backend


def load_config() -> Config:
    logging.info("Loading configuration...")
    load_dotenv()
    config_dict = {f.name: os.getenv(f.name.upper()) for f in fields(Config)}
    config = _from_dict(config_dict)
    logging.info("Configuration loaded")
    set_storage_backend(config)
    logging.info(f"Storage backend set to: {config.storage_backend}")
    return config
