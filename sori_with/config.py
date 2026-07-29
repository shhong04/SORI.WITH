from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLDS = ROOT / "config" / "thresholds.yaml"


class ThresholdConfig(BaseModel):
    sample_rate: int = 48000
    hop_length: int = 512
    onset_energy_percentile: float = 85.0
    min_onset_gap_sec: float = 0.05
    stable_timing_spread_ms: float = 40.0
    drift_timing_spread_ms: float = 80.0
    breakdown_timing_spread_ms: float = 160.0
    min_state_duration_beats: float = 2.0
    tempo_smoothing_window: int = 8
    default_tempo_bpm: float = 120.0
    tempo_min_bpm: float = 70.0
    tempo_max_bpm: float = 160.0
    role_prior: dict[str, float] = Field(
        default_factory=lambda: {
            "drums": 1.4,
            "bass": 1.2,
            "guitar": 1.0,
            "keyboard": 1.0,
            "vocal": 0.8,
        }
    )
    deviation_significance_ms: float = 60.0
    propagation_lag_window_ms: float = 800.0


class Settings(BaseSettings):
    app_name: str = "SORI.WITH"
    api_prefix: str = "/api/v1"
    # development | production — production disables path-based analyze by default
    environment: str = "development"
    data_dir: Path = ROOT / "data"
    upload_dir: Path = ROOT / "data" / "uploads"
    report_dir: Path = ROOT / "data" / "reports"
    thresholds_path: Path = DEFAULT_THRESHOLDS
    # Comma-separated origins. Empty string → deny browser CORS (except non-browser clients).
    cors_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:3000,http://localhost:3000"
    )
    max_upload_bytes: int = 50 * 1024 * 1024
    max_audio_duration_sec: float = 600.0
    # None → enabled only when environment == development
    allow_path_analyze: bool | None = None
    keep_upload_artifacts: bool = False

    model_config = {"env_prefix": "SORI_WITH_"}

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def path_analyze_enabled(self) -> bool:
        if self.allow_path_analyze is not None:
            return self.allow_path_analyze
        return not self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    return settings


@lru_cache
def get_thresholds() -> ThresholdConfig:
    path = get_settings().thresholds_path
    if path.exists():
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return ThresholdConfig.model_validate(raw)
    return ThresholdConfig()
