"""R2 uploader: key derivation and the r2_configured gate. boto3 is mocked."""

from unittest.mock import MagicMock, patch

from ttc_headway import r2
from ttc_headway.config import Settings


def _r2_settings(tmp_path) -> Settings:
    return Settings(
        storage_root=str(tmp_path),
        r2_bucket="bkt",
        r2_endpoint_url="https://acct.r2.cloudflarestorage.com",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
    )


def test_r2_configured_requires_all_four(tmp_path):
    assert _r2_settings(tmp_path).r2_configured is True
    # Missing the secret key -> not configured (must not silently half-work).
    partial = Settings(
        storage_root=str(tmp_path),
        r2_bucket="bkt",
        r2_endpoint_url="https://x",
        r2_access_key_id="key",
    )
    assert partial.r2_configured is False


def test_upload_paths_keys_mirror_partition_layout(tmp_path):
    settings = _r2_settings(tmp_path)
    p1 = tmp_path / "vehicles" / "dt=2026-08-14" / "hour=17" / "vehicles_1710_1720.parquet"
    p2 = tmp_path / "pb" / "dt=2026-08-14" / "hour=17" / "vehicles_1710_1720.pb.gz"
    for p in (p1, p2):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")

    client = MagicMock()
    with patch.object(r2.boto3, "client", return_value=client):
        r2.upload_paths(settings, [p1, p2])

    calls = client.upload_file.call_args_list
    keys = {c.args[2] for c in calls}
    assert keys == {
        "raw/vehicles/dt=2026-08-14/hour=17/vehicles_1710_1720.parquet",
        "raw/pb/dt=2026-08-14/hour=17/vehicles_1710_1720.pb.gz",
    }
    assert all(c.args[1] == "bkt" for c in calls)
