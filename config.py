import os
from dataclasses import dataclass, fields

from dotenv import load_dotenv


@dataclass
class Config:
    spotify_token_url: str
    spotify_client_id: str
    spotify_client_secret: str
    spotify_playlist_id: str
    bot_token: str
    bucket: str
    target_chat_id: str


def _from_dict(dict_: dict) -> Config:
    # Change all the keys to lowercase
    dict_ = {k.lower(): v for k, v in dict_.items()}
    return Config(**dict_)


def load_config() -> Config:
    load_dotenv()
    config_dict = {f.name: os.getenv(f.name.upper()) for f in fields(Config)}
    config = _from_dict(config_dict)
    return config
