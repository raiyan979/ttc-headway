"""Collector orchestration guardrails that need no network."""

from ttc_headway.config import Settings
from ttc_headway.poll import run_cycle


def test_refuses_to_collect_on_actions_without_r2(monkeypatch, tmp_path):
    # On the ephemeral Actions runner, writing locally would lose the data, so
    # the collector must fail closed rather than pretend to succeed.
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    for var in (
        "TTC_R2_BUCKET",
        "TTC_R2_ENDPOINT_URL",
        "TTC_R2_ACCESS_KEY_ID",
        "TTC_R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(storage_root=str(tmp_path), _env_file=None)
    assert run_cycle(settings) == 2
