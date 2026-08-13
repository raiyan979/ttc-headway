"""Publish local cycle files to Cloudflare R2 (S3-compatible).

The collector writes locally first, then calls this to upload. Keys mirror the
local partition layout under a `raw/` prefix, so R2 ends up with:
    raw/vehicles/dt=.../hour=.../vehicles_HHMM_HHMM.parquet
    raw/pb/dt=.../hour=.../vehicles_HHMM_HHMM.pb.gz
Upload is a keyed PUT, so re-running a slot overwrites its objects rather than
duplicating — the same idempotency the local write has.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import boto3

from .config import Settings

log = logging.getLogger("ttc_headway.r2")


def _client(settings: Settings):
    # region_name="auto" is what R2 expects for the S3 API.
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload_paths(settings: Settings, paths: Iterable[Path]) -> None:
    """Upload each local file to R2, keying it by its path relative to storage_root."""
    client = _client(settings)
    root = Path(settings.storage_root)
    for path in paths:
        key = "raw/" + path.relative_to(root).as_posix()
        client.upload_file(str(path), settings.r2_bucket, key)
        log.info("uploaded %s -> s3://%s/%s", path.name, settings.r2_bucket, key)
