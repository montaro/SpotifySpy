from typing import TypeAlias

StorageData: TypeAlias = dict


class Storage:
    @staticmethod
    def get_file(key: str) -> StorageData:
        raise NotImplementedError

    @staticmethod
    def put_file(key: str, data: StorageData) -> StorageData:
        raise NotImplementedError


class FileNotFound(Exception):
    pass


class SaveFileError(Exception):
    pass
