import boto3
import uuid
from app.config import get_settings

settings = get_settings()

s3_client = None

def _get_s3_client():
    global s3_client
    if s3_client is None:
        if not settings.s3_bucket_name:
            raise RuntimeError("S3 storage is not configured. Set S3_BUCKET_NAME and related env vars.")
        client_kwargs = {"region_name": settings.s3_region}
        # Static credentials are optional: on AWS (ECS/EC2/Lambda) the task or
        # instance IAM role supplies them automatically, so only pass explicit
        # keys when they are provided (e.g. local dev or an S3-compatible host).
        if settings.s3_access_key_id and settings.s3_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
        # Custom endpoint only for S3-compatible providers; omit for real AWS S3.
        if settings.s3_endpoint:
            client_kwargs["endpoint_url"] = settings.s3_endpoint
        s3_client = boto3.client("s3", **client_kwargs)
    return s3_client


def upload_image(file_bytes: bytes, filename: str, mimetype: str) -> dict:
    """Upload image to S3, return the key and URL."""

    # generate unique name
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    key = f"notes/{uuid.uuid4()}.{ext}"

    _get_s3_client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=file_bytes,
        ContentType=mimetype,
    )

    # generate a presigned url
    # (or make the bucket public and use a direct URL instead)
    url = _get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key},
        ExpiresIn=604800  # 7 days in seconds
    )

    return {"key": key, "url": url}


def delete_image(key: str) -> None:
    """Delete an image from S3 by its key."""
    _get_s3_client().delete_object(
        Bucket=settings.s3_bucket_name,
        Key=key
    )


def get_fresh_url(key: str) -> str:
    """Generate a fresh presigned URL for an existing key."""
    return _get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key},
        ExpiresIn=604800
    )


def download_image(key: str) -> bytes:
    """Download image bytes from S3 by key."""
    response = _get_s3_client().get_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
    )
    return response["Body"].read()


def generate_presigned_put(key: str, content_type: str, expires_in: int = 3600) -> dict:
    """Presigned URL the browser uses to PUT an image straight to S3.
    Keeps large uploads off the Lambda Function URL (6MB request limit)."""
    url = _get_s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )
    return {"key": key, "url": url}


def put_image(key: str, file_bytes: bytes, mimetype: str) -> str:
    """Overwrite an existing key (e.g. with the HEIC-converted / compressed version)
    and return a fresh presigned GET URL."""
    _get_s3_client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=file_bytes,
        ContentType=mimetype,
    )
    return get_fresh_url(key)