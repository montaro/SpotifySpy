from typing import TypeAlias

StorageData: TypeAlias = dict


class Storage:
    @staticmethod
    def get_file(key: str) -> StorageData:
        pass

    @staticmethod
    def put_file(key: str, data: StorageData) -> StorageData:
        pass


class FileNotFound(Exception):
    pass


class SaveFileError(Exception):
    pass
