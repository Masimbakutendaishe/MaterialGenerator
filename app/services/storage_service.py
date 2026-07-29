# S3/MinIO upload + presigned URL abstraction
"""S3/MinIO abstraction — all file storage goes through here.
Local dev uses MinIO (S3-compatible); swapping to real AWS S3 in production
is just an env var change, no code change."""
import boto3
from botocore.exceptions import ClientError
from botocore.client import Config
from flask import current_app


def _client():
    return boto3.client(
        "s3",
        endpoint_url=current_app.config.get("S3_ENDPOINT_URL"),
        aws_access_key_id=current_app.config.get("S3_ACCESS_KEY"),
        aws_secret_access_key=current_app.config.get("S3_SECRET_KEY"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",  # MinIO ignores this; required by boto3's client either way
    )
def ensure_bucket_exists():
    """Verifies the configured bucket is reachable with current credentials. Does NOT
    attempt to create it — R2 buckets should already exist (created manually in the
    Cloudflare dashboard); attempting creation here would require broader permissions
    than the app's token needs, and masks real credential/config errors as bucket-missing
    errors instead."""
    bucket = current_app.config.get("S3_BUCKET")
    client = _client()
    client.head_bucket(Bucket=bucket)  # raises a clear ClientError if credentials/bucket are wrong


def upload_file(file_bytes: bytes, key: str, content_type: str) -> str:
    """Uploads bytes to storage under the given key. Returns the key (not a URL —
    use get_presigned_url separately, since URLs should be short-lived, not stored)."""
    ensure_bucket_exists()
    bucket = current_app.config.get("S3_BUCKET")
    client = _client()
    client.put_object(Bucket=bucket, Key=key, Body=file_bytes, ContentType=content_type)
    return key


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generates a temporary download URL for a stored file. Default expiry: 1 hour."""
    bucket = current_app.config.get("S3_BUCKET")
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )

def download_file(key: str) -> bytes:
    """Downloads a file's raw bytes from storage. Returns empty bytes if the key doesn't exist,
    rather than raising — callers should treat a missing/failed logo as 'no logo', not a hard error."""
    bucket = current_app.config.get("S3_BUCKET")
    client = _client()
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except ClientError:
        return b""