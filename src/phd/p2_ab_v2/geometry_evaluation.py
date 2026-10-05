"""Exact v1 distance definitions with shared reference trees and parallel queries."""
from __future__ import annotations
import numpy as np
from scipy.spatial import cKDTree
from src.phd.p2_ab_v1.evaluation import distance_summary


class GeometryEvaluator:
    def __init__(self, reference, workers=4):
        self.reference = self.points(reference)
        self.workers = workers
        self.tree = cKDTree(self.reference) if len(self.reference) else None
        self.xy_tree = cKDTree(self.reference[:, :2]) if len(self.reference) else None

    @staticmethod
    def points(x):
        a = np.asarray(x, dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != 3 or not np.isfinite(a).all():
            raise ValueError('finite XYZ [N,3] required')
        return a

    def measure(self, predicted, tolerances=(.25, .5, 1.), xy_radius=.5):
        p, r = self.points(predicted), self.reference
        eps = np.asarray(tolerances, dtype=float)
        if eps.ndim != 1 or not len(eps) or not np.isfinite(eps).all() or (eps <= 0).any():
            raise ValueError('positive finite tolerances required')
        if not np.isfinite(xy_radius) or xy_radius <= 0:
            raise ValueError('positive finite XY radius required')
        forward, reverse = np.full(len(p), np.nan), np.full(len(r), np.inf)
        xy, dz = np.full(len(p), np.inf), np.full(len(p), np.nan)
        if len(p) and len(r):
            forward = self.tree.query(p, workers=self.workers)[0]
            xy, index = self.xy_tree.query(p[:, :2], workers=self.workers)
            supported = xy <= xy_radius
            dz[supported] = p[supported, 2]-r[index[supported], 2]
            reverse = cKDTree(p).query(r, workers=self.workers)[0]
        result = dict(
            prediction_count=len(p), reference_count=len(r), forward_reference_count=len(r),
            reference_status='AVAILABLE' if len(r) else 'REFERENCE_ABSENT',
            prediction_status='PRESENT' if len(p) else 'MISSING',
            prediction_to_reference=distance_summary(forward), reference_to_prediction=distance_summary(reverse),
            xy_nearest_abs_dz=distance_summary(np.abs(dz)),
            xy_nearest_signed_dz_median_m=float(np.nanmedian(dz)) if np.isfinite(dz).any() else None,
            xy_correspondence_radius_m=float(xy_radius), xy_supported_count=int(np.isfinite(dz).sum()),
            xy_support_fraction=float(np.isfinite(dz).mean()) if len(p) and len(r) else None,
            sampling_denominator='native/reference or rendered/prediction points; not surface area',
            reference_accuracy_m=None, scientific_verdict=None, tolerance_sweep=[])
        for e in eps:
            precision, recall = int((forward <= e).sum()), int((reverse <= e).sum())
            result['tolerance_sweep'].append(dict(
                tolerance_m=float(e), predicted_inlier_count=precision,
                prediction_precision=precision/len(p) if len(p) and len(r) else None,
                reference_recovered_count=recall, reference_recall=recall/len(r) if len(r) else None,
                missing_reference_point_count=len(r)-recall if len(r) else None))
        return result
