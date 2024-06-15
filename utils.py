import logging
import os


logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

logging.getLogger("botocore").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("boto3").setLevel(logging.ERROR)

logger = logging.getLogger("spotifyspy")


def get_logger():
    return logger


def sanitize_text(text: str) -> str:
    return (
        text.replace(r"_", r"\_")
        .replace(r"*", r"\*")
        .replace(r"[", r"\[")
        .replace(r"`", r"\`")
        .replace(r"-", r"\-")
        .replace(r"(", r"\(")
        .replace(r")", r"\)")
    )


def mkdir_p(path: str) -> None:
    try:
        os.makedirs(path)
    except FileExistsError:
        pass
    except Exception as e:
        raise e
