import json
import os

from storage import FileNotFound, SaveFileError, Storage, StorageData
from utils import get_logger, mkdir_p


logger = get_logger()


class FilesystemStorage(Storage):
    def __init__(self, config):
        self.config = config
        self.path = os.path.expandvars(self.config.filesystem_storage_path)
        mkdir_p(self.path)

    def _get_file_path(self, key: str) -> str:
        return os.path.join(self.path, key)

    def get_file(self, key: str) -> StorageData:
        file_path = self._get_file_path(key)
        try:
            with open(file_path, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            error_message = f"File: {file_path} does not exist in the filesystem"
            raise FileNotFound(error_message)
        except Exception as e:
            error_message = f"Failed to retrieve file with name: {file_path} from the filesystem"
            logger.error(f"{error_message} with error: {e}")
            raise FileNotFound(error_message)

    def put_file(self, key: str, data: StorageData) -> StorageData:
        file_path = self._get_file_path(key)
        try:
            with open(file_path, "w") as file:
                json.dump(data, file)
                return data
        except Exception as e:
            error_message = f"Failed to store file with name: {file_path} in the filesystem"
            logger.error(f"{error_message} with error: {e}")
            raise SaveFileError(error_message)
