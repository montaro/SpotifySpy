import os


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
