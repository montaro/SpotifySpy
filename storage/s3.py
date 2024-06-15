import io
import json
import logging

import boto3

from storage import FileNotFound, SaveFileError, Storage, StorageData

S3 = "s3"
HTTP_STATUS_CODE = "HTTPStatusCode"
RESPONSE_METADATA = "ResponseMetadata"


class S3Storage(Storage):
    def __init__(self, config):
        self.bucket = config.s3_bucket
        self.client = boto3.client(
            S3, region_name=config.s3_region, aws_access_key_id=config.s3_access_key_id, aws_secret_access_key=config.s3_secret_access_key
        )

    def get_file(self, key: str) -> StorageData:
        try:
            logging.info(f"Retrieving file with key: {key} from S3 bucket: {self.bucket}")
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            data = json.load(response["Body"])
            logging.info(f"Retrieved file with key: {key} from S3 bucket: {self.bucket}")
            return data
        except self.client.exceptions.NoSuchKey:
            error_message = f"File: {key} does not exist in the S3 bucket: {self.bucket}"
            logging.error(error_message)
            raise FileNotFound(error_message)
        except Exception as e:
            error_message = f"Failed to retrieve file with key: {key} from S3 bucket: {self.bucket}"
            logging.error(f"{error_message} with error: {e}")
            raise FileNotFound(error_message)

    def put_file(self, key: str, data: StorageData) -> StorageData:
        logging.info(f"Storing file: {key} in S3 bucket: {self.bucket} with key: {key}")
        try:
            file_like_object = io.StringIO()
            json.dump(obj=data, fp=file_like_object)
            file_like_object.seek(0)
            response = self.client.put_object(Body=file_like_object.getvalue().encode(), Bucket=self.bucket, Key=key)
            if response[RESPONSE_METADATA][HTTP_STATUS_CODE] == 200:
                logging.info(f"File with key: {key} stored successfully in S3 bucket: {self.bucket}")
            else:
                logging.error(
                    f"Failed to store the file with key: {key} in the S3 bucket: {self.bucket} "
                    f"with status code: {response[RESPONSE_METADATA][HTTP_STATUS_CODE]} and response: {response}"
                )
            return response
        except Exception as e:
            error_message = f"Failed to store file with key: {key} in S3 bucket: {self.bucket}"
            logging.error(f"{error_message} with error: {e}")
            raise SaveFileError(error_message)
