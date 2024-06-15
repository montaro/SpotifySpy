import json
import logging

from storage import Storage, FileNotFound, SaveFileError, StorageData
from utils import mkdir_p


class FilesystemStorage(Storage):
    def __init__(self, config):
        mkdir_p(config.filesystem_storage_path)

    def get_file(self, key: str) -> StorageData:
        try:
            with open(key, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            error_message = f"File: {key} does not exist in the filesystem"
            raise FileNotFound(error_message)
        except Exception as e:
            error_message = f"Failed to retrieve file with name: {key} from the filesystem"
            logging.error(f"{error_message} with error: {e}")
            raise FileNotFound(error_message)

    def put_file(self, key: str, data: StorageData) -> StorageData:
        try:
            with open(key, 'w') as file:
                json.dump(data, file)
                return data
        except Exception as e:
            error_message = f"Failed to store file with name: {key} in the filesystem"
            logging.error(f"{error_message} with error: {e}")
            raise SaveFileError(error_message)
