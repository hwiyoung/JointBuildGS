"""Reference-integrity tests for the S1 verify-page bundle contract.

Contract: ``phd_s3_verify_s1_bundle_v1`` (S3 redesign verification pages, §2:
"참조 무결성 자동 테스트(tests/) — 실패 = 런 불합격").

Bundle root resolution order:
1. env ``JBGS_S3_VERIFY_ROOT`` (must point at the bundle root containing ``runs/``)
2. ``$JBGS_ARTIFACT_ROOT/phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1`` when the env var is set
3. container default ``/artifacts/JointBuildGS/phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1``
4. host default    ``.../JointBuildGS-artifacts/phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1``

If no bundle root (or no ``runs/<name>/``) exists yet, every test skips —
the bundle has simply not been generated. Once at least one run exists,
every discovered run is validated strictly; any violation fails the run.

Per contract, GT planes are evaluation-only, ALS points (source==1) are
overlay-only and never inlier targets, ``scientific_verdict`` stays null,
and ``not_official`` stays true.
"""

from __future__ import annotations

import json
import numbers
import os
import unittest
from pathlib import Path

import numpy as np

BUNDLE_ENV = "JBGS_S3_VERIFY_ROOT"
ARTIFACT_ROOT_ENV = "JBGS_ARTIFACT_ROOT"
BUNDLE_RELPATH = Path("phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1")
DEFAULT_BUNDLE_ROOTS = (
    Path("/artifacts/JointBuildGS") / BUNDLE_RELPATH,
    Path(
        "/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts"
    )
    / BUNDLE_RELPATH,
)

SCHEMA = "phd_s3_verify_s1_bundle_v1"
MANIFEST_REQUIRED_KEYS = (
    "schema",
    "bundle_name",
    "stage",
    "s1_mode",
    "dataset",
    "crs",
    "local_offset",
    "inlier_def",
    "prereg",
    "counts",
    "thinning",
    "scientific_verdict",
    "not_official",
)
COUNTS_REQUIRED_KEYS = ("points_total", "points_mvs", "points_als", "planes", "orphans")
THINNING_REQUIRED_KEYS = ("max_points", "stride", "original_count")
INLIER_DEF_REQUIRED_KEYS = ("tau_m", "support_buffer_m", "target", "definition")
PLANE_REQUIRED_KEYS = (
    "plane_id",
    "source",
    "n",
    "d",
    "support_local",
    "inlier_idx",
    "inlier_count",
    "inlier_rms_m",
    "gravity_angle_deg",
    "gt_match",
)
PLANE_SOURCES = {
    "prior",
    "mvs",
    "footprint",
    "gapfill",
    "synthetic_gt",
    "synthetic_distractor",
}
GT_PLANE_REQUIRED_KEYS = ("gt_plane_id", "n", "d", "support_local", "matched_plane_ids")
GT_MATCH_REQUIRED_KEYS = ("gt_plane_id", "angle_deg", "offset_m")
VIEW_REQUIRED_KEYS = ("footprint_local", "ground_z", "top_z", "gravity")

SOURCE_MVS = 0
SOURCE_ALS = 1

# Contract vertex layout: x,y,z float32 + red,green,blue uchar + source uchar.
PLY_FLOAT_TYPES = {"float", "float32"}
PLY_UCHAR_TYPES = {"uchar", "uint8"}
PLY_EXPECTED_PROPERTIES = (
    (PLY_FLOAT_TYPES, "x"),
    (PLY_FLOAT_TYPES, "y"),
    (PLY_FLOAT_TYPES, "z"),
    (PLY_UCHAR_TYPES, "red"),
    (PLY_UCHAR_TYPES, "green"),
    (PLY_UCHAR_TYPES, "blue"),
    (PLY_UCHAR_TYPES, "source"),
)
PLY_VERTEX_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
        ("source", "u1"),
    ]
)
PLY_VERTEX_SIZE = PLY_VERTEX_DTYPE.itemsize  # 16 bytes


def resolve_bundle_root() -> Path | None:
    """Return the first existing bundle root candidate, or None."""
    candidates: list[Path] = []
    env_root = os.environ.get(BUNDLE_ENV)
    if env_root:
        candidates.append(Path(env_root))
    artifact_root = os.environ.get(ARTIFACT_ROOT_ENV)
    if artifact_root:
        candidates.append(Path(artifact_root) / BUNDLE_RELPATH)
    candidates.extend(DEFAULT_BUNDLE_ROOTS)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def discover_run_dirs(bundle_root: Path | None) -> list[Path]:
    """All runs/<name>/ directories, sorted by name; [] when absent."""
    if bundle_root is None:
        return []
    runs_root = bundle_root / "runs"
    if not runs_root.is_dir():
        return []
    return sorted(p for p in runs_root.iterdir() if p.is_dir())


def parse_ply_header(raw: bytes, path: Path) -> tuple[list[tuple[str, str, str]], int, int]:
    """Parse an ASCII PLY header from raw file bytes with the standard library.

    Returns (elements, vertex_count, data_offset) where elements is a flat
    list of (element_name, property_type, property_name) rows in file order.
    Raises AssertionError on any contract violation.
    """
    end_marker = b"end_header\n"
    end = raw.find(end_marker)
    assert end != -1, f"{path}: no end_header marker"
    data_offset = end + len(end_marker)
    header_lines = raw[:end].decode("ascii").splitlines()
    assert header_lines, f"{path}: empty header"
    assert header_lines[0].strip() == "ply", f"{path}: missing 'ply' magic line"

    fmt: str | None = None
    elements: list[tuple[str, str, str]] = []
    element_order: list[tuple[str, int]] = []
    current_element: str | None = None
    for line in header_lines[1:]:
        tokens = line.strip().split()
        if not tokens or tokens[0] == "comment" or tokens[0] == "obj_info":
            continue
        if tokens[0] == "format":
            assert tokens[1:] == ["binary_little_endian", "1.0"], (
                f"{path}: format must be 'binary_little_endian 1.0', got {tokens[1:]}"
            )
            fmt = tokens[1]
        elif tokens[0] == "element":
            assert len(tokens) == 3, f"{path}: malformed element line {line!r}"
            current_element = tokens[1]
            element_order.append((tokens[1], int(tokens[2])))
        elif tokens[0] == "property":
            assert current_element is not None, f"{path}: property before element"
            assert tokens[1] != "list", (
                f"{path}: list properties are outside the s1_points contract"
            )
            assert len(tokens) == 3, f"{path}: malformed property line {line!r}"
            elements.append((current_element, tokens[1], tokens[2]))
        else:
            raise AssertionError(f"{path}: unexpected header line {line!r}")
    assert fmt == "binary_little_endian", f"{path}: missing format line"
    assert len(element_order) == 1 and element_order[0][0] == "vertex", (
        f"{path}: exactly one 'vertex' element required, got {element_order}"
    )
    vertex_count = element_order[0][1]
    assert vertex_count >= 0, f"{path}: negative vertex count"
    return elements, vertex_count, data_offset


def load_ply_points(path: Path) -> np.ndarray:
    """Load s1_points.ply into a structured array after strict layout checks."""
    raw = path.read_bytes()
    elements, vertex_count, data_offset = parse_ply_header(raw, path)
    assert len(elements) == len(PLY_EXPECTED_PROPERTIES), (
        f"{path}: expected {len(PLY_EXPECTED_PROPERTIES)} vertex properties, "
        f"got {len(elements)}: {elements}"
    )
    for (elem_name, prop_type, prop_name), (allowed_types, expected_name) in zip(
        elements, PLY_EXPECTED_PROPERTIES
    ):
        assert elem_name == "vertex", f"{path}: property on unexpected element {elem_name}"
        assert prop_name == expected_name, (
            f"{path}: property order must be x y z red green blue source; "
            f"found {prop_name!r} where {expected_name!r} expected"
        )
        assert prop_type in allowed_types, (
            f"{path}: property {prop_name!r} must be one of {sorted(allowed_types)}, "
            f"got {prop_type!r}"
        )
    body_size = len(raw) - data_offset
    assert body_size == vertex_count * PLY_VERTEX_SIZE, (
        f"{path}: binary body is {body_size} bytes, expected "
        f"{vertex_count} vertices x {PLY_VERTEX_SIZE} bytes"
    )
    return np.frombuffer(raw, dtype=PLY_VERTEX_DTYPE, count=vertex_count, offset=data_offset)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def is_number(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def as_index_array(values, path: Path, label: str) -> np.ndarray:
    assert isinstance(values, list), f"{path}: {label} must be a list"
    for value in values:
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"{path}: {label} entries must be integers, got {value!r}"
        )
    return np.asarray(values, dtype=np.int64)


_BUNDLE_CACHE: dict[Path, dict] = {}


def load_bundle(run_dir: Path) -> dict:
    """Load and cache one run's files; missing files raise AssertionError."""
    cached = _BUNDLE_CACHE.get(run_dir)
    if cached is not None:
        return cached
    required = {
        "manifest": run_dir / "manifest.json",
        "planes": run_dir / "s1_planes.json",
        "orphans": run_dir / "s1_orphans.json",
        "view": run_dir / "s1_view.json",
    }
    ply_path = run_dir / "s1_points.ply"
    missing = [str(p) for p in [*required.values(), ply_path] if not p.is_file()]
    assert not missing, f"{run_dir.name}: missing bundle files: {missing}"
    bundle = {name: load_json(path) for name, path in required.items()}
    bundle["points"] = load_ply_points(ply_path)
    bundle["run_dir"] = run_dir
    _BUNDLE_CACHE[run_dir] = bundle
    return bundle


class S1BundleReferenceIntegrityTest(unittest.TestCase):
    """Strict reference-integrity validation for every discovered S1 run."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle_root = resolve_bundle_root()
        cls.run_dirs = discover_run_dirs(cls.bundle_root)

    def setUp(self) -> None:
        if not self.run_dirs:
            self.skipTest(
                "S1 verify bundle not generated yet: no runs/<name>/ found under "
                f"env {BUNDLE_ENV}, {ARTIFACT_ROOT_ENV}/{BUNDLE_RELPATH}, or defaults "
                f"{[str(p) for p in DEFAULT_BUNDLE_ROOTS]}"
            )

    def for_each_run(self, check) -> None:
        """Run one check per discovered run inside a subTest scope.

        A failing run is recorded as that run's subtest failure while the
        remaining runs are still validated.
        """
        for run_dir in self.run_dirs:
            with self.subTest(run=run_dir.name):
                check(run_dir.name, load_bundle(run_dir))

    # ---------------------------------------------------------------- manifest

    def test_manifest_contract_fields(self) -> None:
        self.for_each_run(self._check_manifest_contract_fields)

    def _check_manifest_contract_fields(self, name: str, bundle: dict) -> None:
        manifest = bundle["manifest"]
        for key in MANIFEST_REQUIRED_KEYS:
            self.assertIn(key, manifest, f"{name}: manifest missing key {key!r}")
        self.assertEqual(manifest["schema"], SCHEMA, f"{name}: wrong schema string")
        self.assertIn(manifest["stage"],
                      ("s1", "s1+s2", "s1+s2+s3a", "s1+s2+s3a+s3b",
                       "s1+s2+s3a+s3b+s3c"),
                      f"{name}: stage must be 's1' or a later cumulative stage "
                      "up to 's1+s2+s3a+s3b+s3c'")
        self.assertEqual(
            manifest["bundle_name"], name,
            f"{name}: manifest bundle_name must match runs/<name>/ directory",
        )
        self.assertIsNone(
            manifest["scientific_verdict"],
            f"{name}: scientific_verdict must stay null",
        )
        self.assertIs(
            manifest["not_official"], True, f"{name}: not_official must be true"
        )

        dataset = manifest["dataset"]
        self.assertIsInstance(dataset, dict, f"{name}: dataset must be an object")
        self.assertIn(
            dataset.get("kind"), ("real", "synthetic"),
            f"{name}: dataset.kind must be 'real' or 'synthetic'",
        )
        expected_crs = "EPSG:25832" if dataset["kind"] == "real" else "local"
        self.assertEqual(
            manifest["crs"], expected_crs,
            f"{name}: crs must be {expected_crs!r} for dataset.kind={dataset['kind']!r}",
        )

        offset = manifest["local_offset"]
        self.assertIsInstance(offset, list, f"{name}: local_offset must be a list")
        self.assertEqual(len(offset), 3, f"{name}: local_offset must have 3 entries")
        for value in offset:
            self.assertTrue(is_number(value), f"{name}: local_offset entry {value!r}")

        inlier_def = manifest["inlier_def"]
        for key in INLIER_DEF_REQUIRED_KEYS:
            self.assertIn(key, inlier_def, f"{name}: inlier_def missing {key!r}")
        self.assertTrue(
            is_number(inlier_def["tau_m"]) and inlier_def["tau_m"] > 0,
            f"{name}: inlier_def.tau_m must be a positive number",
        )
        self.assertTrue(
            is_number(inlier_def["support_buffer_m"])
            and inlier_def["support_buffer_m"] >= 0,
            f"{name}: inlier_def.support_buffer_m must be a non-negative number",
        )
        self.assertEqual(
            inlier_def["target"], "mvs_current",
            f"{name}: inlier_def.target must be 'mvs_current'",
        )
        self.assertTrue(
            isinstance(inlier_def["definition"], str)
            and inlier_def["definition"].strip(),
            f"{name}: inlier_def.definition must be a non-empty string",
        )

        prereg = manifest["prereg"]
        self.assertIs(
            prereg.get("proposal"), True,
            f"{name}: prereg must be marked as proposal (\"proposal\": true)",
        )
        self.assertTrue(
            is_number(prereg.get("orphan_ratio_max"))
            and 0 < prereg["orphan_ratio_max"] <= 1,
            f"{name}: prereg.orphan_ratio_max must be a number in (0, 1]",
        )
        gt_match_prereg = prereg.get("gt_match")
        self.assertIsInstance(
            gt_match_prereg, dict, f"{name}: prereg.gt_match must be an object"
        )
        for key in ("max_angle_deg", "max_offset_m"):
            self.assertTrue(
                is_number(gt_match_prereg.get(key)) and gt_match_prereg[key] > 0,
                f"{name}: prereg.gt_match.{key} must be a positive number",
            )

        counts = manifest["counts"]
        for key in COUNTS_REQUIRED_KEYS:
            self.assertTrue(
                isinstance(counts.get(key), int)
                and not isinstance(counts.get(key), bool)
                and counts[key] >= 0,
                f"{name}: counts.{key} must be a non-negative integer",
            )
        self.assertEqual(
            counts["points_mvs"] + counts["points_als"],
            counts["points_total"],
            f"{name}: counts.points_mvs + counts.points_als must equal counts.points_total",
        )

        thinning = manifest["thinning"]
        for key in THINNING_REQUIRED_KEYS:
            self.assertTrue(
                isinstance(thinning.get(key), int)
                and not isinstance(thinning.get(key), bool)
                and thinning[key] >= 0,
                f"{name}: thinning.{key} must be a non-negative integer",
            )
        self.assertGreaterEqual(
            thinning["stride"], 1, f"{name}: thinning.stride must be >= 1"
        )
        self.assertLessEqual(
            counts["points_total"], thinning["max_points"],
            f"{name}: points_total exceeds thinning.max_points",
        )
        self.assertLessEqual(
            counts["points_total"], thinning["original_count"],
            f"{name}: points_total exceeds thinning.original_count",
        )

    # ------------------------------------------------------------------ points

    def test_points_ply_layout_and_counts(self) -> None:
        self.for_each_run(self._check_points_ply_layout_and_counts)

    def _check_points_ply_layout_and_counts(self, name: str, bundle: dict) -> None:
        points = bundle["points"]  # load_ply_points already checked the layout
        counts = bundle["manifest"]["counts"]
        self.assertEqual(
            len(points), counts["points_total"],
            f"{name}: s1_points.ply vertex count != counts.points_total",
        )
        source = points["source"]
        invalid = np.unique(source[(source != SOURCE_MVS) & (source != SOURCE_ALS)])
        self.assertEqual(
            invalid.size, 0,
            f"{name}: source values must be 0(mvs_current)/1(als_prior); "
            f"found {invalid.tolist()}",
        )
        n_mvs = int(np.count_nonzero(source == SOURCE_MVS))
        n_als = int(np.count_nonzero(source == SOURCE_ALS))
        self.assertEqual(
            n_mvs, counts["points_mvs"],
            f"{name}: source==0 point count != counts.points_mvs",
        )
        self.assertEqual(
            n_als, counts["points_als"],
            f"{name}: source==1 point count != counts.points_als",
        )
        for axis in ("x", "y", "z"):
            self.assertTrue(
                bool(np.isfinite(points[axis]).all()),
                f"{name}: non-finite {axis} coordinates in s1_points.ply",
            )

    # ------------------------------------------------------------------ planes

    def test_planes_reference_integrity(self) -> None:
        self.for_each_run(self._check_planes_reference_integrity)

    def _check_planes_reference_integrity(self, name: str, bundle: dict) -> None:
        planes_doc = bundle["planes"]
        points = bundle["points"]
        counts = bundle["manifest"]["counts"]
        total = counts["points_total"]
        source = points["source"]
        planes_path = bundle["run_dir"] / "s1_planes.json"

        self.assertIs(
            planes_doc.get("gt_evaluation_only"), True,
            f"{name}: s1_planes.json gt_evaluation_only must be true",
        )
        planes = planes_doc.get("planes")
        self.assertIsInstance(planes, list, f"{name}: planes must be a list")
        self.assertEqual(
            len(planes), counts["planes"],
            f"{name}: len(planes) != counts.planes",
        )

        plane_ids = [plane.get("plane_id") for plane in planes]
        self.assertEqual(
            len(plane_ids), len(set(plane_ids)),
            f"{name}: duplicate plane_id values: "
            f"{sorted({p for p in plane_ids if plane_ids.count(p) > 1})}",
        )

        for plane in planes:
            pid = plane.get("plane_id")
            for key in PLANE_REQUIRED_KEYS:
                self.assertIn(
                    key, plane, f"{name}/{pid}: plane missing key {key!r}"
                )
            self.assertTrue(
                isinstance(pid, str) and pid,
                f"{name}: plane_id must be a non-empty string, got {pid!r}",
            )
            self.assertIn(
                plane["source"], PLANE_SOURCES,
                f"{name}/{pid}: plane source {plane['source']!r} not in contract set",
            )
            self.assertEqual(
                len(plane["n"]), 3, f"{name}/{pid}: plane normal n must have 3 entries"
            )
            self.assertTrue(
                all(is_number(v) for v in plane["n"]) and is_number(plane["d"]),
                f"{name}/{pid}: n/d must be numeric",
            )
            self.assertTrue(
                is_number(plane["gravity_angle_deg"])
                and 0 <= plane["gravity_angle_deg"] <= 180,
                f"{name}/{pid}: gravity_angle_deg must be in [0, 180]",
            )
            support = plane["support_local"]
            self.assertTrue(
                isinstance(support, list) and len(support) >= 3,
                f"{name}/{pid}: support_local needs at least 3 vertices",
            )
            for vertex in support:
                self.assertEqual(
                    len(vertex), 3,
                    f"{name}/{pid}: support_local vertices must be [x, y, z]",
                )

            idx = as_index_array(
                plane["inlier_idx"], planes_path, f"{pid}.inlier_idx"
            )
            self.assertEqual(
                int(plane["inlier_count"]), idx.size,
                f"{name}/{pid}: inlier_count != len(inlier_idx)",
            )
            if idx.size:
                self.assertTrue(
                    is_number(plane["inlier_rms_m"]) and plane["inlier_rms_m"] >= 0,
                    f"{name}/{pid}: inlier_rms_m must be a non-negative number",
                )
                self.assertTrue(
                    bool((idx >= 0).all()) and bool((idx < total).all()),
                    f"{name}/{pid}: inlier_idx out of [0, {total})",
                )
                self.assertEqual(
                    idx.size, np.unique(idx).size,
                    f"{name}/{pid}: duplicate indices inside inlier_idx",
                )
                plane_sources = source[idx]
                bad = int(np.count_nonzero(plane_sources != SOURCE_MVS))
                self.assertEqual(
                    bad, 0,
                    f"{name}/{pid}: {bad} inlier indices point at non-mvs points "
                    "(ALS/source==1 points are overlay-only, never inliers)",
                )

    # ---------------------------------------------------------------- gt match

    def test_gt_match_mutual_consistency(self) -> None:
        self.for_each_run(self._check_gt_match_mutual_consistency)

    def _check_gt_match_mutual_consistency(self, name: str, bundle: dict) -> None:
        planes_doc = bundle["planes"]
        planes = planes_doc.get("planes", [])
        gt_planes = planes_doc.get("gt_planes")
        self.assertIsInstance(
            gt_planes, list, f"{name}: gt_planes must be a list"
        )

        gt_ids = [gt.get("gt_plane_id") for gt in gt_planes]
        self.assertEqual(
            len(gt_ids), len(set(gt_ids)),
            f"{name}: duplicate gt_plane_id values",
        )
        plane_ids = {plane["plane_id"] for plane in planes}

        # forward: plane.gt_match -> gt_planes
        forward: dict[str, str] = {}
        for plane in planes:
            pid = plane["plane_id"]
            gt_match = plane.get("gt_match")
            if gt_match is None:
                continue
            self.assertIsInstance(
                gt_match, dict, f"{name}/{pid}: gt_match must be null or an object"
            )
            for key in GT_MATCH_REQUIRED_KEYS:
                self.assertIn(
                    key, gt_match, f"{name}/{pid}: gt_match missing key {key!r}"
                )
            self.assertTrue(
                is_number(gt_match["angle_deg"]) and is_number(gt_match["offset_m"]),
                f"{name}/{pid}: gt_match angle_deg/offset_m must be numeric",
            )
            gt_id = gt_match["gt_plane_id"]
            self.assertIn(
                gt_id, set(gt_ids),
                f"{name}/{pid}: gt_match references unknown gt_plane_id {gt_id!r}",
            )
            forward[pid] = gt_id

        # backward: gt_planes.matched_plane_ids -> planes, and mutual agreement
        backward: dict[str, str] = {}
        for gt in gt_planes:
            gt_id = gt["gt_plane_id"]
            for key in GT_PLANE_REQUIRED_KEYS:
                self.assertIn(
                    key, gt, f"{name}/{gt_id}: gt_plane missing key {key!r}"
                )
            matched = gt["matched_plane_ids"]
            self.assertIsInstance(
                matched, list,
                f"{name}/{gt_id}: matched_plane_ids must be a list",
            )
            self.assertEqual(
                len(matched), len(set(matched)),
                f"{name}/{gt_id}: duplicate entries in matched_plane_ids",
            )
            for pid in matched:
                self.assertIn(
                    pid, plane_ids,
                    f"{name}/{gt_id}: matched_plane_ids references unknown "
                    f"plane_id {pid!r}",
                )
                # Face-side rule is "any candidate within thresholds counts":
                # one plane may legitimately cover several nearly-coplanar GT
                # faces (GT subdivision), so multi-face membership is allowed.
                backward.setdefault(pid, set()).add(gt_id)

        for pid, gt_id in forward.items():
            self.assertIn(
                gt_id, backward.get(pid, set()),
                f"{name}: plane {pid!r} gt_match -> {gt_id!r} but that face's "
                "matched_plane_ids does not list the plane",
            )
        for pid in backward:
            self.assertIn(
                pid, forward,
                f"{name}: plane {pid!r} listed in matched_plane_ids but "
                "carries no gt_match",
            )

    # ----------------------------------------------------------------- orphans

    def test_orphans_reference_integrity(self) -> None:
        self.for_each_run(self._check_orphans_reference_integrity)

    def _check_orphans_reference_integrity(self, name: str, bundle: dict) -> None:
        orphans_doc = bundle["orphans"]
        points = bundle["points"]
        counts = bundle["manifest"]["counts"]
        total = counts["points_total"]
        points_mvs = counts["points_mvs"]
        orphans_path = bundle["run_dir"] / "s1_orphans.json"

        self.assertIn(
            "orphan_idx", orphans_doc, f"{name}: s1_orphans.json missing orphan_idx"
        )
        self.assertIn(
            "orphan_ratio", orphans_doc,
            f"{name}: s1_orphans.json missing orphan_ratio",
        )
        orphan_idx = as_index_array(
            orphans_doc["orphan_idx"], orphans_path, "orphan_idx"
        )
        self.assertEqual(
            orphan_idx.size, counts["orphans"],
            f"{name}: len(orphan_idx) != counts.orphans",
        )
        if orphan_idx.size:
            self.assertTrue(
                bool((orphan_idx >= 0).all()) and bool((orphan_idx < total).all()),
                f"{name}: orphan_idx out of [0, {total})",
            )
            self.assertEqual(
                orphan_idx.size, np.unique(orphan_idx).size,
                f"{name}: duplicate indices inside orphan_idx",
            )

        inlier_mask = np.zeros(total, dtype=bool)
        for plane in bundle["planes"].get("planes", []):
            idx = np.asarray(plane["inlier_idx"], dtype=np.int64)
            if idx.size:
                inlier_mask[idx] = True
        orphan_mask = np.zeros(total, dtype=bool)
        if orphan_idx.size:
            orphan_mask[orphan_idx] = True

        overlap = int(np.count_nonzero(orphan_mask & inlier_mask))
        self.assertEqual(
            overlap, 0,
            f"{name}: {overlap} points are both an orphan and a plane inlier",
        )

        # Exact contract definition: orphan set == {source==0} minus all inliers.
        expected_orphan_mask = (points["source"] == SOURCE_MVS) & ~inlier_mask
        mismatch = int(np.count_nonzero(orphan_mask != expected_orphan_mask))
        self.assertEqual(
            mismatch, 0,
            f"{name}: orphan_idx differs from recomputed "
            "(source==0 and not inlier of any plane) set at "
            f"{mismatch} indices",
        )

        ratio = orphans_doc["orphan_ratio"]
        self.assertTrue(is_number(ratio), f"{name}: orphan_ratio must be a number")
        if points_mvs == 0:
            self.assertEqual(
                orphan_idx.size, 0,
                f"{name}: orphans exist but counts.points_mvs == 0",
            )
            self.assertEqual(
                ratio, 0, f"{name}: orphan_ratio must be 0 when no mvs points"
            )
        else:
            expected_ratio = orphan_idx.size / points_mvs
            self.assertAlmostEqual(
                ratio, expected_ratio, delta=1e-6,
                msg=(
                    f"{name}: orphan_ratio {ratio} != recomputed "
                    f"{expected_ratio} (= {orphan_idx.size}/{points_mvs})"
                ),
            )

    # -------------------------------------------------------------------- view

    def test_view_required_keys(self) -> None:
        self.for_each_run(self._check_view_required_keys)

    def _check_view_required_keys(self, name: str, bundle: dict) -> None:
        view = bundle["view"]
        for key in VIEW_REQUIRED_KEYS:
            self.assertIn(key, view, f"{name}: s1_view.json missing key {key!r}")
        footprint = view["footprint_local"]
        self.assertTrue(
            isinstance(footprint, list) and len(footprint) >= 3,
            f"{name}: footprint_local needs at least 3 vertices",
        )
        for vertex in footprint:
            self.assertEqual(
                len(vertex), 2, f"{name}: footprint_local vertices must be [x, y]"
            )
            self.assertTrue(
                all(is_number(v) for v in vertex),
                f"{name}: footprint_local vertices must be numeric",
            )
        self.assertTrue(
            is_number(view["ground_z"]) and is_number(view["top_z"]),
            f"{name}: ground_z/top_z must be numeric",
        )
        self.assertGreaterEqual(
            view["top_z"], view["ground_z"],
            f"{name}: top_z must be >= ground_z",
        )
        gravity = view["gravity"]
        self.assertEqual(len(gravity), 3, f"{name}: gravity must have 3 entries")
        self.assertTrue(
            all(is_number(v) for v in gravity),
            f"{name}: gravity entries must be numeric",
        )
        self.assertGreater(
            float(np.linalg.norm(np.asarray(gravity, dtype=np.float64))), 0.0,
            f"{name}: gravity vector must be non-zero",
        )


if __name__ == "__main__":
    unittest.main()
