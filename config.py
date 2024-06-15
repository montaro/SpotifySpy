import argparse
import os
from dataclasses import dataclass, fields

from dotenv import load_dotenv

import constants
from storage import Storage
from storage.filesystem import FilesystemStorage
from storage.s3 import S3Storage
from utils import get_logger


logger = get_logger()

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
    check_interval: int = 60


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
    global _storage_backend
    return _storage_backend


def _raise_missing_config_value_error(f_name: str):
    logger.error(f"The argument --{f_name} was not provided and the corresponding environment variable {f_name.upper()} was not set.")
    exit(1)


def load_config() -> Config:
    logger.info("Loading configuration...")
    load_dotenv()
    parser = argparse.ArgumentParser()
    for f in fields(Config):
        f_name = f.name
        parser.add_argument(f"--{f_name}", default=os.getenv(f_name.upper()))
    args = parser.parse_args()
    config_dict = {f.name: getattr(args, f.name) for f in fields(Config)}
    config = _from_dict(config_dict)
    storage_storage_info_msg = ""
    if config.storage_backend is None:
        logger.warning("No storage backend provided, using the filesystem storage backend")
        config.storage_backend = constants.STORAGE_FILESYSTEM
    else:
        match config.storage_backend:
            case constants.STORAGE_FILESYSTEM:
                if config.filesystem_storage_path is None:
                    config.filesystem_storage_path = os.getcwd()
                    logger.warning(f"No storage path provided, using the current directory: {config.filesystem_storage_path}")
                storage_storage_info_msg = f"Storage path set to: {config.filesystem_storage_path}"
            case constants.STORAGE_S3:
                if config.s3_region is None:
                    _raise_missing_config_value_error("s3_region")
                storage_storage_info_msg = f"Storage region set to: {config.s3_region}"
                if config.s3_bucket is None:
                    _raise_missing_config_value_error("s3_bucket")
                storage_storage_info_msg = f"{storage_storage_info_msg}, Storage bucket set to: {config.s3_bucket}"
                if config.s3_access_key_id is None:
                    _raise_missing_config_value_error("s3_access_key_id")
                if config.s3_secret_access_key is None:
                    _raise_missing_config_value_error("s3_secret_access_key")
            case _:
                raise ValueError(
                    f"Invalid storage backend, the only valid values are: {constants.STORAGE_FILESYSTEM} and {constants.STORAGE_S3}"
                )
    logger.info("Configuration loaded")
    set_storage_backend(config)
    logger.info(f"Storage backend is set to: {config.storage_backend}")
    logger.info(storage_storage_info_msg)
    return config
