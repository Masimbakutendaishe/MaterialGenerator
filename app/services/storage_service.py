# S3/MinIO upload + presigned URL abstraction
"""S3/MinIO abstraction — all file storage goes through here.
Local dev uses MinIO (S3-compatible); swapping to real AWS S3 in production
is just an env var change, no code change."""
import boto3
from botocore.exceptions import ClientError
from botocore.client import Config
from flask import current_app


def _client():
    access_key = current_app.config.get("S3_ACCESS_KEY")
    import sys
    print(f"[DEBUG] Using S3_ACCESS_KEY starting with: {access_key[:8] if access_key else 'NONE'}...", flush=True, file=sys.stderr)
    return boto3.client(
        "s3",
        endpoint_url=current_app.config.get("S3_ENDPOINT_URL"),
        aws_access_key_id=access_key,
        aws_secret_access_key=current_app.config.get("S3_SECRET_KEY"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )
def ensure_bucket_exists():
    """No-op: R2 buckets are created manually in the Cloudflare dashboard and always
    expected to exist. Checking via head_bucket requires bucket-level permissions some
    R2 API tokens don't grant even when scoped to full object read/write — so we skip
    the check entirely and let the actual upload/download call surface any real error."""
    pass


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