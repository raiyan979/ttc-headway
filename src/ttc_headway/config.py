"""Runtime configuration.

pydantic-settings so every value is env-overridable (prefix TTC_) and can be
supplied from a gitignored .env locally or from GitHub Actions secrets in CI.
Analytical thresholds (bunching ratios, etc.) live in dbt vars, not here — this
file is only the collector's runtime knobs.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TTC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Feed ---
    feed_url: str = "https://bustime.ttc.ca/gtfsrt/vehicles"
    # Be identifiable to the agency: a researcher, not anonymous abuse.
    user_agent: str = (
        "ttc-headway/0.1 (+https://github.com/raiyan979/ttc-headway; research, contact via repo)"
    )

    # --- Poll cadence ---
    # 30s resolution is the measurement floor: you cannot resolve a bunching
    # event shorter than your sampling interval.
    poll_interval_s: int = 30
    # ~9.5 min of a 10-min cron slot, leaving headroom to write and exit before
    # the next scheduled run.
    cycle_duration_s: int = 570

    # --- HTTP hardening ---
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 20.0
    max_retries: int = 3
    # Cap the read before parsing untrusted protobuf — an unbounded read of a
    # hostile or malfunctioning endpoint is a memory-exhaustion vector.
    max_response_bytes: int = 20 * 1024 * 1024

    # --- Storage ---
    # Local path for dev, or s3://<bucket> for R2.
    storage_root: str = "./data/raw"
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
