"""End-to-end B-mode reconstruction orchestration."""

from dataclasses import dataclass

import numpy as np

from .beamforming import delay_and_sum
from .config import ImagingConfig
from .metrics import QualityMetrics, evaluate_cyst
from .processing import (
    envelope_detect,
    log_compress,
    scan_convert_linear,
    time_gain_compensation,
)
from .simulation import Phantom, make_cyst_phantom, simulate_channel_data


@dataclass(frozen=True)
class BModeResult:
    channel_data: np.ndarray
    beamformed_rf: np.ndarray
    envelope: np.ndarray
    bmode_db: np.ndarray
    metrics: QualityMetrics
    phantom: Phantom
    config: ImagingConfig


def run_pipeline(
    config: ImagingConfig | None = None,
    phantom: Phantom | None = None,
    seed: int = 7,
) -> BModeResult:
    """Simulate acquisition, reconstruct B-mode, and evaluate the cyst."""
    config = config or ImagingConfig()
    phantom = phantom or make_cyst_phantom(config, seed=seed)
    channel = simulate_channel_data(phantom, config, seed=seed + 12)
    rf = delay_and_sum(channel, config)
    envelope = envelope_detect(rf)
    compensated = time_gain_compensation(
        envelope,
        config.depth_axis_m,
        config.center_frequency_hz,
        config.tgc_db_cm_mhz,
    )
    bmode_db = scan_convert_linear(log_compress(compensated, config.dynamic_range_db))
    metrics = evaluate_cyst(compensated, config.line_positions_m, config.depth_axis_m)
    return BModeResult(channel, rf, compensated, bmode_db, metrics, phantom, config)

