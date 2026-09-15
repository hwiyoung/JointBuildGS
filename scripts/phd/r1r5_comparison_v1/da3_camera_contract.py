"""Validate the exact float32 camera representation returned by pinned DA3."""
import numpy as np


def validate_camera_return(predicted, original):
    expected = np.asarray(original)[:, :3, :].astype(np.float32)
    actual = np.asarray(predicted)
    if (actual.dtype != np.float32 or actual.shape != expected.shape
            or not np.isfinite(actual).all() or not np.isfinite(expected).all()
            or not np.array_equal(actual, expected)):
        raise ValueError("DA3 output camera differs from the exact float32 input representation")
    return dict(policy="EXACT_FLOAT32_INPUT_CAMERA_EQUALITY", dtype=str(actual.dtype),
                max_float64_conversion_error=float(np.max(np.abs(
                    actual.astype(np.float64) - np.asarray(original)[:, :3, :]))))
