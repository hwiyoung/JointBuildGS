#!/usr/bin/env python3
"""Generate a read-only document, lineage, and run inventory for JointBuildGS."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import unquote, urlsplit


MARKDOWN_LINK_RE = re.compile(r"(!?)\[[^\]]*\]\(([^)]+)\)")
REPO_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:docs|phases|results|reports|configs|scripts|src|tools|data|artifacts)/"
    r"[^\s,`\"'<>|)\]}]+)"
)
RUN_ID_RE = re.compile(r"(?<![0-9])((?:20[0-9]{6}_[A-Za-z0-9_.-]+)|(?:[ewt][0-9][A-Za-z0-9_.-]*_20[0-9]{6}(?:_[0-9]{6})?))(?![A-Za-z0-9_.-])", re.IGNORECASE)
DATE_RE = re.compile(r"(?<![0-9])(20[0-9]{6})(?![0-9])")
VERSION_RE = re.compile(r"(?<![A-Za-z0-9])v([0-9]+(?:[._][0-9]+)*)(?![A-Za-z0-9])", re.IGNORECASE)
ROLE_TOKENS = {
    "ambiguous",
    "boundary_cases",
    "candidates",
    "change_report",
    "coefficients",
    "conditional_targets",
    "confusion",
    "diagnostics",
    "inventory",
    "issues",
    "ladder",
    "manifest",
    "measurements",
    "metrics",
    "pairs",
    "readout",
    "report",
    "sensitivity",
    "summary",
    "targets",
}
TRAILING_REFERENCE_PUNCTUATION = ".,;:!?"


@dataclass(frozen=True)
class Relation:
    source_path: str
    relation: str
    target_path: str
    target_exists: str
    evidence: str
    confidence: str
    line: int | str


def run_git(
    repo_root: Path,
    args: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "git",
        "-c",
        f"safe.directory={repo_root}",
        "-c",
        "core.quotepath=false",
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=repo_root,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return result


def git_z_paths(repo_root: Path, args: Sequence[str]) -> list[str]:
    output = run_git(repo_root, args).stdout
    return [part.decode("utf-8", errors="surrogateescape") for part in output.split(b"\0") if part]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema_version") != 1:
        raise ValueError("repo inventory config schema_version must be 1")
    reviewed_document_map(config)
    return config


def reviewed_document_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    allowed_statuses = {"canonical", "supporting", "superseded", "retracted", "draft", "temporary"}
    reviewed: dict[str, dict[str, Any]] = {}
    for family in config.get("reviewed_family_maps", []):
        family_id = str(family["family_id"])
        decision_record = str(family["decision_record"])
        for document in family.get("documents", []):
            item = dict(document)
            path = str(item["path"])
            status = str(item["status"])
            if status not in allowed_statuses:
                raise ValueError(f"unsupported reviewed status for {path}: {status}")
            if path in reviewed:
                raise ValueError(f"duplicate reviewed document path: {path}")
            item["reviewed_family_id"] = family_id
            item["decision_record"] = decision_record
            item["reviewed_on"] = str(family.get("reviewed_on", ""))
            reviewed[path] = item
    return reviewed


def load_path_migrations(repo_root: Path, config: dict[str, Any]) -> dict[str, dict[str, str]]:
    migrations: dict[str, dict[str, str]] = {}
    new_paths: set[str] = set()
    required = {"migration_id", "old_path", "new_path", "lifecycle_status", "old_path_retained", "sha256"}
    for manifest_path in config.get("path_migration_manifests", []):
        absolute = repo_root / str(manifest_path)
        if not absolute.is_file():
            raise ValueError(f"path migration manifest is absent: {manifest_path}")
        with absolute.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError(f"path migration manifest schema mismatch: {manifest_path}")
            for row in reader:
                old_path = row["old_path"]
                new_path = row["new_path"]
                if old_path in migrations:
                    raise ValueError(f"duplicate migrated old path: {old_path}")
                if new_path in new_paths:
                    raise ValueError(f"duplicate migrated new path: {new_path}")
                retained = row["old_path_retained"]
                if retained not in {"true", "false"}:
                    raise ValueError(f"invalid old_path_retained for {old_path}: {retained}")
                expected_sha = row["sha256"]
                if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
                    raise ValueError(f"invalid migration SHA-256 for {old_path}")
                new_absolute = repo_root / new_path
                if not new_absolute.is_file():
                    raise ValueError(f"migrated target is absent: {new_path}")
                actual_sha = hashlib.sha256(new_absolute.read_bytes()).hexdigest()
                if actual_sha != expected_sha:
                    raise ValueError(f"migrated target hash mismatch: {new_path}")
                old_absolute = repo_root / old_path
                if old_absolute.exists() != (retained == "true"):
                    raise ValueError(f"old-path retention mismatch: {old_path}")
                if retained == "true" and hashlib.sha256(old_absolute.read_bytes()).hexdigest() != expected_sha:
                    raise ValueError(f"compatibility mirror hash mismatch: {old_path}")
                migrations[old_path] = dict(row)
                new_paths.add(new_path)
    return migrations


def apply_path_migrations(
    repo_root: Path,
    relations: Sequence[Relation],
    migrations: dict[str, dict[str, str]],
) -> list[Relation]:
    resolved: list[Relation] = []
    old_source_by_new_path = {row["new_path"]: old_path for old_path, row in migrations.items()}
    for relation in relations:
        target_path = relation.target_path
        confidence = relation.confidence

        # A byte-preserving document move also preserves its historical relative
        # link text. Resolve that text from the former source directory before
        # applying target migrations, rather than rewriting frozen evidence.
        old_source_path = old_source_by_new_path.get(relation.source_path)
        if old_source_path is not None and relation.target_exists == "no":
            historical = resolve_reference(old_source_path, relation.evidence, repo_root)
            if historical is not None:
                historical_target, historical_exists = historical
                if historical_target in migrations or historical_exists == "yes":
                    target_path = historical_target
                    confidence = f"{confidence}+historical_source_path"

        migration = migrations.get(target_path)
        if migration is None:
            if target_path == relation.target_path:
                resolved.append(relation)
            else:
                resolved.append(
                    Relation(
                        relation.source_path,
                        relation.relation,
                        target_path,
                        "yes" if (repo_root / target_path).exists() else "no",
                        relation.evidence,
                        confidence,
                        relation.line,
                    )
                )
            continue
        new_path = migration["new_path"]
        resolved.append(
            Relation(
                relation.source_path,
                relation.relation,
                new_path,
                "yes" if (repo_root / new_path).exists() else "no",
                relation.evidence,
                f"{confidence}+path_migration",
                relation.line,
            )
        )
    return resolved


def find_repo_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    result = subprocess.run(
        ["git", "-c", f"safe.directory={start}", "-C", str(start), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "not inside a Git repository")
    return Path(result.stdout.strip()).resolve()


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def is_document_scope(path: str, config: dict[str, Any]) -> bool:
    excluded = set(config["generated_paths"]) | set(config.get("inventory_control_paths", []))
    if path in excluded:
        return False
    if any(path == root or path.startswith(f"{root}/") for root in config["document_roots"]):
        return True
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in config["phase_document_globs"])


def normalized_token(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def family_id_for(path: str, config: dict[str, Any]) -> str:
    parts = PurePosixPath(path).parts
    name = PurePosixPath(path).name.lower()
    if path == "docs/README.md":
        return "docs_index"
    if path == "phases/README.md":
        return "phase_index"
    if len(parts) >= 3 and parts[0] == "phases" and name in {"readme.md", "agents.md", "claude.md", "issues.md"}:
        return f"{phase_for(path).lower()}_{PurePosixPath(path).stem.lower()}"
    for rule in config.get("family_rules", []):
        if re.search(rule["pattern"], path):
            return rule["family_id"]

    if len(parts) >= 4 and parts[0] == "docs" and parts[1] in {"figs", "experiments", "archive", "evidence"}:
        return normalized_token(parts[2]) or "unclassified"

    stem = PurePosixPath(path).stem
    stem = DATE_RE.sub("", stem)
    stem = VERSION_RE.sub("", stem)
    stem = re.sub(r"(?i)^(?:w|report)[_-]", "", stem)
    stem = re.sub(r"(?i)(?:[_-](?:tmp|temp|draft|final|latest))+$", "", stem)
    token = normalized_token(stem)
    if not token:
        return "unclassified"
    pieces = [piece for piece in token.split("_") if piece not in ROLE_TOKENS]
    return "_".join(pieces) or token


def version_label_for(path: str, family_id: str, config: dict[str, Any]) -> str:
    match = VERSION_RE.search(path)
    if match:
        return f"v{match.group(1).replace('.', '_')}"
    for rule in config.get("implicit_version_rules", []):
        if family_id == rule["family_id"] and re.search(rule["pattern"], path):
            return rule["version"]
    return ""


def version_tuple(label: str) -> tuple[int, ...] | None:
    if not label or not label.lower().startswith("v"):
        return None
    try:
        return tuple(int(part) for part in re.split(r"[._]", label[1:]))
    except ValueError:
        return None


def lineage_key_for(path: str) -> str:
    stem = unicodedata.normalize("NFKC", PurePosixPath(path).stem).lower()
    stem = DATE_RE.sub("", stem)
    stem = VERSION_RE.sub("", stem)
    stem = re.sub(r"^(?:w|report)[_-]", "", stem)
    stem = re.sub(r"[_-]+", "_", stem).strip("_")
    return stem


def phase_for(path: str) -> str:
    if path.startswith("phases/p0-audit/"):
        return "P0"
    if path.startswith("phases/p2-gsjso/"):
        return "P2"
    return "repo"


def artifact_kind_for(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    name = PurePosixPath(path).name.lower()
    if suffix in {".md", ".rst", ".txt"}:
        return "document"
    if suffix in {".csv", ".tsv", ".parquet"}:
        return "table"
    if suffix in {".json", ".yaml", ".yml", ".toml"}:
        if "manifest" in name or "receipt" in name:
            return "manifest"
        return "structured_record"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}:
        return "figure"
    if suffix in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".odt"}:
        return "binary_document"
    if suffix in {".py", ".sh"}:
        return "script"
    return "other"


def document_type_for(path: str, artifact_kind: str) -> str:
    name = PurePosixPath(path).name.lower()
    stem = PurePosixPath(path).stem.lower()
    if name in {"readme.md", "agents.md", "claude.md"}:
        return "guide"
    if "research_context" in name:
        return "research_context"
    if "experiment_plan" in name or "실험계획" in name:
        return "experiment_plan"
    if "사전등록" in name or "prereg" in name or "lock" in name or "잠금" in name:
        return "preregistration_or_lock"
    if "issues" in stem:
        return "issue_log"
    if "manifest" in stem or "receipt" in stem:
        return "manifest_or_receipt"
    if "summary" in stem or stem.startswith("w_") or "report" in stem or "보고" in stem:
        return "report"
    if artifact_kind == "table":
        return "evidence_table"
    if artifact_kind == "figure":
        return "figure"
    return artifact_kind


def storage_class_for(path: str, artifact_kind: str, size: int) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if any(token in path.lower() for token in ("/__pycache__/", "/cache/", "/logs/")):
        return "D"
    if suffix in {".las", ".laz", ".ply", ".obj", ".npz", ".npy", ".pt", ".ckpt"} or size >= 100 * 1024 * 1024:
        return "C"
    if artifact_kind in {"figure", "binary_document"}:
        return "B-candidate"
    return "A"


def read_text_limited(path: Path, limit: int) -> tuple[str, bool]:
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    truncated = len(payload) > limit
    return payload[:limit].decode("utf-8", errors="replace"), truncated


def clean_markdown_target(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        return raw[1 : raw.index(">")]
    if re.search(r"\s+[\"']", raw):
        raw = re.split(r"\s+[\"']", raw, maxsplit=1)[0]
    return raw.strip()


def resolve_reference(source_path: str, raw_target: str, repo_root: Path) -> tuple[str, str] | None:
    target = unquote(raw_target.strip())
    try:
        split = urlsplit(target)
    except ValueError:
        return target, "no"
    if split.scheme or split.netloc or target.startswith("#"):
        return None
    target = split.path
    if not target:
        return None
    target = target.replace("\\", "/")
    if "/JointBuildGS/" in target:
        target = target.split("/JointBuildGS/", 1)[1]
    elif target.startswith("/"):
        target = target.lstrip("/")
    elif target.startswith(("docs/", "phases/", "results/", "reports/", "configs/", "scripts/", "src/", "tools/", "data/", "artifacts/")):
        pass
    elif target.startswith("runs/") and source_path.startswith("phases/"):
        phase_root = "/".join(PurePosixPath(source_path).parts[:2])
        target = f"{phase_root}/{target}"
    else:
        target = posixpath.join(posixpath.dirname(source_path), target)
    target = posixpath.normpath(target)
    if target == ".." or target.startswith("../"):
        return target, "no"
    try:
        exists = (repo_root / target).exists()
    except OSError:
        exists = False
    return target, "yes" if exists else "no"


def path_mentions(text: str) -> Iterator[tuple[str, int]]:
    for match in REPO_PATH_RE.finditer(text):
        target = match.group(1).rstrip(TRAILING_REFERENCE_PUNCTUATION)
        yield target, text.count("\n", 0, match.start()) + 1


def parse_front_matter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    metadata: dict[str, Any] = {}
    current_list: str | None = None
    for raw_line in text[4:end].splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        list_match = re.match(r"^\s+-\s+(.+?)\s*$", raw_line)
        if list_match and current_list:
            metadata.setdefault(current_list, []).append(list_match.group(1).strip("\"'"))
            continue
        key_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", raw_line)
        if not key_match:
            current_list = None
            continue
        key, value = key_match.groups()
        if value:
            metadata[key] = value.strip("\"'")
            current_list = None
        else:
            metadata[key] = []
            current_list = key
    return metadata


def lineage_metadata(text: str, suffix: str) -> dict[str, Any]:
    if suffix == ".md":
        return parse_front_matter(text)
    if suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {
                key: parsed[key]
                for key in ("family_id", "version", "status", "canonical_for", "run_ids", "supersedes", "derived_from")
                if key in parsed
            }
    return {}


def scan_relations(
    repo_root: Path,
    source_path: str,
    text_extensions: set[str],
    limit: int,
) -> tuple[list[Relation], set[str], bool, dict[str, Any]]:
    suffix = PurePosixPath(source_path).suffix.lower()
    if suffix not in text_extensions:
        return [], set(), False, {}
    absolute = repo_root / source_path
    if not absolute.is_file():
        return [], set(), False, {}
    text, truncated = read_text_limited(absolute, limit)
    metadata = lineage_metadata(text, suffix)
    relations: list[Relation] = []
    seen: set[tuple[str, str]] = set()
    run_ids = set(RUN_ID_RE.findall(text))

    metadata_runs = metadata.get("run_ids", [])
    if isinstance(metadata_runs, str):
        metadata_runs = [metadata_runs]
    if isinstance(metadata_runs, list):
        run_ids.update(str(item) for item in metadata_runs)

    for metadata_key, relation_name in (("supersedes", "supersedes"), ("derived_from", "derived_from")):
        values = metadata.get(metadata_key, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for raw_target_value in values:
            raw_target = str(raw_target_value)
            resolved = resolve_reference(source_path, raw_target, repo_root)
            if resolved is None:
                continue
            target, exists = resolved
            key = (relation_name, target)
            if key not in seen:
                relations.append(Relation(source_path, relation_name, target, exists, raw_target, "explicit_metadata", 1))
                seen.add(key)

    for match in MARKDOWN_LINK_RE.finditer(text):
        raw_target = clean_markdown_target(match.group(2))
        resolved = resolve_reference(source_path, raw_target, repo_root)
        if resolved is None:
            continue
        target, exists = resolved
        line = text.count("\n", 0, match.start()) + 1
        relation_name = "embeds" if match.group(1) else "references"
        key = (relation_name, target)
        if key not in seen:
            relations.append(Relation(source_path, relation_name, target, exists, raw_target, "explicit", line))
            seen.add(key)

    for raw_target, line in path_mentions(text):
        resolved = resolve_reference(source_path, raw_target, repo_root)
        if resolved is None:
            continue
        target, exists = resolved
        key = ("mentions_path", target)
        if key not in seen:
            relations.append(Relation(source_path, "mentions_path", target, exists, raw_target, "text", line))
            seen.add(key)
        run_ids.update(RUN_ID_RE.findall(target))

    return relations, run_ids, truncated, metadata


def history_map(repo_root: Path, scoped_paths: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    if not scoped_paths:
        return {}, {}
    output = run_git(
        repo_root,
        ["log", "--format=@@%H", "--name-only", "--no-renames", "HEAD", "--", "docs", "phases"],
    ).stdout.decode("utf-8", errors="surrogateescape")
    newest: dict[str, str] = {}
    oldest: dict[str, str] = {}
    commit = ""
    for line in output.splitlines():
        if line.startswith("@@"):
            commit = line[2:]
            continue
        if not line or not commit or line not in scoped_paths:
            continue
        newest.setdefault(line, commit)
        oldest[line] = commit
    return oldest, newest


def indexed_size(repo_root: Path, path: str) -> int:
    absolute = repo_root / path
    if absolute.exists() or absolute.is_symlink():
        return absolute.lstat().st_size
    result = run_git(repo_root, ["cat-file", "-s", f":{path}"], check=False)
    if result.returncode == 0:
        return int(result.stdout.strip())
    return 0


def initial_status(path: str, canonical: dict[str, dict[str, str]]) -> tuple[str, str, str, str]:
    lower = path.lower()
    name = PurePosixPath(path).name.lower()
    if path in canonical:
        item = canonical[path]
        return "canonical", "explicit_repo_rule", item["canonical_for"], item["reason"]
    if "/archive/" in lower:
        return "superseded", "archive_path", "", "Path is already under an archive directory."
    if name == "retracted.md" or "retracted" in name:
        return "retracted", "filename", "", "Filename carries an explicit retraction marker."
    if re.search(r"(?:^|[_-])(?:tmp|temp)(?:[_.-]|$)", name):
        return "temporary", "filename", "", "Filename carries a temporary marker."
    if "draft" in name:
        return "draft", "filename", "", "Filename carries a draft marker."
    return "supporting", "default_inventory", "", "No explicit canonical or lifecycle marker was found."


def add_reviewed_relations(
    repo_root: Path,
    reviewed: dict[str, dict[str, Any]],
    relations: list[Relation],
) -> None:
    for path, item in reviewed.items():
        successor = item.get("superseded_by")
        if successor:
            target = str(successor)
            relations.append(
                Relation(
                    target,
                    "supersedes",
                    path,
                    "yes" if (repo_root / path).exists() else "no",
                    str(item["decision_record"]),
                    "reviewed_family_map",
                    "",
                )
            )
        derived_from = item.get("derived_from", [])
        if isinstance(derived_from, str):
            derived_from = [derived_from]
        for source in derived_from:
            source_path = str(source)
            relations.append(
                Relation(
                    path,
                    "derived_from",
                    source_path,
                    "yes" if (repo_root / source_path).exists() else "no",
                    str(item["decision_record"]),
                    "reviewed_family_map",
                    "",
                )
            )


def add_version_candidates(rows: list[dict[str, Any]], relations: list[Relation]) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        parsed = version_tuple(row["version"])
        if parsed is None:
            continue
        groups[(row["family_id"], row["lineage_key"], row["extension"])].append(row)

    for group_rows in groups.values():
        versions = sorted({version_tuple(row["version"]) for row in group_rows if version_tuple(row["version"]) is not None})
        if len(versions) < 2:
            continue
        by_version: dict[tuple[int, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in group_rows:
            parsed = version_tuple(row["version"])
            if parsed is not None:
                by_version[parsed].append(row)
        highest = versions[-1]
        for row in group_rows:
            parsed = version_tuple(row["version"])
            if row["artifact_kind"] == "figure":
                continue
            if row["status_source"] in {"explicit_repo_rule", "explicit_metadata", "reviewed_family_map"}:
                continue
            if parsed == highest:
                row["proposed_status"] = "canonical_candidate"
                row["status_source"] = "highest_filename_version"
                row["status_note"] = "Highest filename version in a comparable path group; human approval required."
            else:
                row["proposed_status"] = "superseded_candidate"
                row["status_source"] = "lower_filename_version"
                row["status_note"] = "A higher filename version exists in a comparable path group; successor must be reviewed."

        for older, newer in zip(versions, versions[1:]):
            older_rows = sorted(by_version[older], key=lambda item: item["path"])
            newer_rows = sorted(by_version[newer], key=lambda item: item["path"])
            if len(older_rows) == 1 and len(newer_rows) == 1:
                relations.append(
                    Relation(
                        newer_rows[0]["path"],
                        "candidate_supersedes",
                        older_rows[0]["path"],
                        "yes",
                        "matching family/lineage key and adjacent filename versions",
                        "filename_candidate",
                        "",
                    )
                )


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def ignored_paths(repo_root: Path, paths: Sequence[str]) -> set[str]:
    if not paths:
        return set()
    payload = b"\0".join(path.encode("utf-8", errors="surrogateescape") for path in paths) + b"\0"
    result = run_git(repo_root, ["check-ignore", "-z", "--stdin"], input_bytes=payload, check=False)
    return {
        item.decode("utf-8", errors="surrogateescape").rstrip("/")
        for item in result.stdout.split(b"\0")
        if item
    }


def build_run_rows(
    repo_root: Path,
    config: dict[str, Any],
    tracked_paths: list[str],
    head_paths: set[str],
    document_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    run_specs: list[tuple[str, str, str]] = []
    for root_spec in config["run_roots"]:
        root_path = repo_root / root_spec["path"]
        if not root_path.is_dir():
            continue
        for entry in sorted(root_path.iterdir(), key=lambda item: item.name):
            if entry.is_dir() and not entry.is_symlink():
                relative = entry.relative_to(repo_root).as_posix()
                run_specs.append((root_spec["phase"], root_spec["path"], relative))

    ignored = ignored_paths(repo_root, [spec[2] for spec in run_specs])
    documents_by_run: Counter[str] = Counter()
    for row in document_rows:
        for run_id in filter(None, row["run_ids"].split(";")):
            documents_by_run[run_id] += 1

    rows: list[dict[str, Any]] = []
    for phase, run_root, run_path in run_specs:
        prefix = f"{run_path}/"
        children = [path for path in tracked_paths if path.startswith(prefix)]
        run_id = PurePosixPath(run_path).name
        direct_names = {
            item.name.lower()
            for item in (repo_root / run_path).iterdir()
            if item.is_file() and not item.is_symlink()
        }
        manifests = sorted(path for path in children if "manifest" in PurePosixPath(path).name.lower())
        versions = sorted(path for path in children if PurePosixPath(path).name.lower() in {"versions.txt", "version.txt"})
        reports = sorted(
            path
            for path in children
            if PurePosixPath(path).name.lower() in {"report.md", "readme.md", "status.md", "summary.md"}
            or "report" in PurePosixPath(path).stem.lower()
        )
        retracted = any(PurePosixPath(path).name.lower() == "retracted.md" for path in children) or "retracted.md" in direct_names
        superseded = any("supersed" in PurePosixPath(path).name.lower() for path in children) or any("supersed" in name for name in direct_names)
        if children:
            state = "tracked_record_present"
            if any(path not in head_paths for path in children):
                state = "indexed_record_present"
        elif run_path in ignored:
            state = "ignored_no_tracked_record"
        else:
            state = "untracked_no_tracked_record"

        issues: list[str] = []
        if not manifests:
            issues.append("missing_tracked_manifest")
        if not versions:
            issues.append("missing_tracked_versions")
        if not reports:
            issues.append("missing_tracked_report_or_index")
        if state.endswith("no_tracked_record"):
            issues.append("no_tracked_run_receipt")
        date_match = DATE_RE.search(run_id)
        rows.append(
            {
                "phase": phase,
                "run_id": run_id,
                "path": run_path,
                "date": date_match.group(1) if date_match else "",
                "git_state": state,
                "tracked_file_count": len(children),
                "tracked_bytes": sum(indexed_size(repo_root, path) for path in children),
                "manifest_count": len(manifests),
                "manifest_paths": ";".join(manifests),
                "version_record_count": len(versions),
                "version_paths": ";".join(versions),
                "report_or_index_count": len(reports),
                "report_or_index_paths": ";".join(reports),
                "retracted_marker": "yes" if retracted else "no",
                "superseded_marker": "yes" if superseded else "no",
                "linked_document_count": documents_by_run[run_id],
                "proposed_storage_class": "A+D/C" if children else "D-review",
                "issues": ";".join(issues),
                "run_root": run_root,
            }
        )
    return rows


def markdown_table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(value) for value in headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def target_bucket(family_id: str, rows: Sequence[dict[str, Any]]) -> str:
    joined = family_id.lower()
    phases = {row["phase"] for row in rows}
    if phases == {"P0"}:
        return "phases/p0-audit/docs/"
    if phases == {"P2"}:
        return "phases/p2-gsjso/docs/"
    if family_id == "docs_index":
        return "docs/README.md"
    if family_id == "phase_index":
        return "phases/README.md"
    if family_id in {"evidence_cards", "judgment_kit"}:
        return f"docs/evidence/{family_id}/"
    if all(row["artifact_kind"] == "figure" for row in rows):
        return f"docs/figs/{family_id}/"
    if any(token in joined for token in ("research_context", "experiment_plan", "사전등록", "prereg", "policy", "audit")):
        return "docs/research/"
    if all(row["proposed_status"] in {"retracted", "superseded", "superseded_candidate"} for row in rows):
        return f"docs/archive/{family_id}/"
    return f"docs/experiments/{family_id}/"


def write_canonical_map(
    path: Path,
    rows: list[dict[str, Any]],
    run_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        families[row["family_id"]].append(row)
    explicit = [row for row in rows if row["status_source"] == "explicit_repo_rule"]
    reviewed_paths = set(reviewed_document_map(config))
    candidate_families = sorted(
        (
            item
            for item in families.items()
            if not all(row["path"] in reviewed_paths for row in item[1])
            and (
                len(item[1]) > 1
                or any(row["proposed_status"] in {"canonical", "canonical_candidate"} for row in item[1])
            )
        ),
        key=lambda item: (-len(item[1]), item[0]),
    )
    rows_by_path = {row["path"]: row for row in rows}
    boundary_review = next(
        (family for family in config.get("reviewed_family_maps", []) if family["family_id"] == "boundary_map"),
        None,
    )
    boundary_rows = sorted(
        (rows_by_path[item["path"]] for item in boundary_review.get("documents", []) if item["path"] in rows_by_path)
        if boundary_review
        else families.get("boundary_map", []),
        key=lambda row: row["path"],
    )
    boundary_runs = sorted(
        (
            row
            for row in run_rows
            if "boundary_map" in row["run_id"].lower() or "anchor_census" in row["run_id"].lower()
        ),
        key=lambda row: row["run_id"],
    )

    lines = [
        "# Canonical document map",
        "",
        "> Generated by `scripts/repo_inventory.py`. `_candidate` values are filename/link heuristics, not approvals.",
        "",
        "## Explicit canonical seeds",
        "",
    ]
    if explicit:
        lines.append(
            markdown_table(
                [(row["canonical_for"], f"`{row['path']}`", row["status_note"]) for row in explicit],
                ["Canonical purpose", "Path", "Evidence"],
            )
        )
    else:
        lines.append("No explicit canonical seeds were configured.")

    lines.extend(["", "## Reviewed family maps", ""])
    reviewed_table: list[tuple[Any, ...]] = []
    for family in config.get("reviewed_family_maps", []):
        documents = family.get("documents", [])
        counts = Counter(str(item["status"]) for item in documents)
        reviewed_table.append(
            (
                family["family_id"],
                f"`{family['decision_record']}`",
                family.get("reviewed_on", ""),
                counts["canonical"],
                counts["supporting"],
                counts["superseded"],
                counts["temporary"],
            )
        )
    if reviewed_table:
        lines.append(
            markdown_table(
                reviewed_table,
                ["Family", "Decision record", "Reviewed", "Canonical", "Supporting", "Superseded", "Temporary"],
            )
        )
    else:
        lines.append("No family-level review has been completed.")

    lines.extend(
        [
            "",
            "## Priority families requiring review",
            "",
            "This table shows multi-file families and explicit/candidate canonical families. Single-file families remain in `DOCUMENT_CATALOG.csv`.",
            "",
        ]
    )
    family_table: list[tuple[Any, ...]] = []
    for family_id, family_rows in candidate_families:
        versions = sorted({row["version"] for row in family_rows if row["version"]}, key=lambda label: version_tuple(label) or ())
        candidates = [row["path"] for row in family_rows if row["proposed_status"] in {"canonical", "canonical_candidate"}]
        family_table.append(
            (
                family_id,
                len(family_rows),
                ", ".join(versions) or "-",
                len(candidates),
                target_bucket(family_id, family_rows),
            )
        )
    lines.append(markdown_table(family_table, ["Family", "Files", "Versions seen", "Canonical candidates", "Target owner path"]))

    lines.extend(["", "## Reviewed pilot: boundary_map", ""])
    if boundary_review:
        lines.append(
            f"The lifecycle decisions below are reviewed in `{boundary_review['decision_record']}`. "
            "The paths shown are current; the exact boundary-map relocations are recorded in "
            "`docs/catalog/migrations/BOUNDARY_MAP_PATHS.csv`, with payload bytes and scientific judgments unchanged."
        )
    else:
        lines.append("This family remains an unreviewed migration pilot.")
    lines.append("")
    if boundary_rows:
        lines.append(
            markdown_table(
                [
                    (
                        f"`{row['path']}`",
                        row["version"] or "-",
                        row["artifact_kind"],
                        row["proposed_status"],
                        row["run_ids"] or "-",
                    )
                    for row in boundary_rows
                ],
                ["Current path", "Version", "Kind", "Lifecycle status", "Referenced run IDs"],
            )
        )
    else:
        lines.append("No boundary-map files were found in the configured document scope.")
    lines.extend(["", "### Related run directories", ""])
    if boundary_runs:
        lines.append(
            markdown_table(
                [(row["run_id"], row["git_state"], row["manifest_count"], row["issues"] or "-") for row in boundary_runs],
                ["Run ID", "Git state", "Tracked manifests", "Issues"],
            )
        )
    else:
        lines.append("No boundary-map run directories were found.")
    lines.extend(
        [
            "",
            "## Approval rule",
            "",
            "Before moving any family, approve the old-to-new path manifest and reference rewrite preview. Canonical review and path migration remain separate tasks and commits.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_issues(
    path: Path,
    rows: list[dict[str, Any]],
    relations: list[Relation],
    run_rows: list[dict[str, Any]],
    max_rows: int,
) -> None:
    broken = sorted(
        (
            relation
            for relation in relations
            if relation.relation in {"references", "embeds"} and relation.target_exists == "no"
        ),
        key=lambda relation: (relation.source_path, str(relation.line), relation.target_path),
    )
    root_docs = [row for row in rows if row["path"].startswith("docs/") and row["path"].count("/") == 1]
    orphan_candidates = [row for row in rows if row["proposed_status"] == "orphan_candidate"]
    family_counts = Counter(row["family_id"] for row in root_docs)
    status_counts = Counter(row["proposed_status"] for row in rows)
    run_state_counts = Counter(row["git_state"] for row in run_rows)
    run_issues = [row for row in run_rows if row["issues"]]

    lines = [
        "# Repository catalog issues",
        "",
        "> Generated report. It records review work; it does not authorize cleanup or make scientific verdicts.",
        "",
        "## Snapshot",
        "",
        markdown_table(
            [
                ("Cataloged indexed files", len(rows)),
                ("Files directly under docs/", len(root_docs)),
                ("Distinct inferred families", len({row["family_id"] for row in rows})),
                ("Local Markdown links/embeds that do not resolve", len(broken)),
                ("Run directories", len(run_rows)),
                ("Run directories with one or more record gaps", len(run_issues)),
            ],
            ["Measure", "Count"],
        ),
        "",
        "### Catalog document statuses",
        "",
        markdown_table(sorted(status_counts.items()), ["Status", "Files"]),
        "",
        "### Run Git states",
        "",
        markdown_table(sorted(run_state_counts.items()), ["Git state", "Runs"]),
        "",
        "## Issue 1: docs-root sprawl",
        "",
        f"`docs/` currently has {len(root_docs)} indexed files directly at its root. The target architecture gives each experiment family one owner directory; no file is moved by this task.",
        "",
        markdown_table(family_counts.most_common(50), ["Inferred family", "Root files"]),
        "",
        "## Issue 2: unresolved local Markdown links",
        "",
    ]
    if broken:
        lines.append(
            markdown_table(
                [
                    (
                        f"`{relation.source_path}`",
                        relation.line,
                        relation.evidence,
                        f"`{relation.target_path}`",
                    )
                    for relation in broken[:max_rows]
                ],
                ["Source", "Line", "Raw target", "Resolved target"],
            )
        )
        if len(broken) > max_rows:
            lines.append("")
            lines.append(f"Only the first {max_rows} of {len(broken)} unresolved links are shown; the lineage CSV retains all parsed relations.")
    else:
        lines.append("No unresolved local Markdown links were found in the scanned text range.")

    lines.extend(
        [
            "",
            "## Issue 3: run receipt gaps",
            "",
            "These are gaps against the target run contract, not claims that a historical run violated the rules in force when it was created.",
            "",
        ]
    )
    if run_issues:
        lines.append(
            markdown_table(
                [(row["phase"], row["run_id"], row["git_state"], row["issues"]) for row in run_issues],
                ["Phase", "Run ID", "Git state", "Issues"],
            )
        )
    else:
        lines.append("No run receipt gaps were detected by the configured minimum markers.")

    lines.extend(["", "## Issue 4: orphan candidates", ""])
    lines.append(
        "A file is an orphan candidate only when it has no parsed inbound path reference and is not an explicit canonical seed, guide, manifest, or figure. This is a triage signal, not proof that the file is unnecessary."
    )
    lines.append("")
    if orphan_candidates:
        lines.append(
            markdown_table(
                [(f"`{row['path']}`", row["family_id"], row["document_type"]) for row in orphan_candidates[:max_rows]],
                ["Path", "Family", "Type"],
            )
        )
        if len(orphan_candidates) > max_rows:
            lines.append("")
            lines.append(f"Only the first {max_rows} of {len(orphan_candidates)} orphan candidates are shown.")
    else:
        lines.append("No orphan candidates were found.")

    lines.extend(
        [
            "",
            "## Required human decisions before migration",
            "",
            "1. Approve the target structure and metadata contract.",
            "2. For one family, approve canonical, supporting, superseded, retracted, and draft statuses.",
            "3. Distinguish broken links from intentionally unavailable external/local artifacts.",
            "4. Decide which run payloads are class C versus regenerable class D.",
            "5. Review an exact path/reference migration preview before any move.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_inventory(repo_root: Path, config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Relation], list[dict[str, Any]]]:
    tracked_paths = git_z_paths(repo_root, ["ls-files", "-z"])
    head_paths = set(git_z_paths(repo_root, ["ls-tree", "-r", "--name-only", "-z", "HEAD"]))
    staged_paths = set(git_z_paths(repo_root, ["diff", "--cached", "--name-only", "-z"]))
    modified_paths = set(git_z_paths(repo_root, ["diff", "--name-only", "-z"]))
    scoped_paths = sorted(path for path in tracked_paths if is_document_scope(path, config))
    oldest, newest = history_map(repo_root, set(scoped_paths))
    canonical = {item["path"]: item for item in config.get("canonical_documents", [])}
    reviewed = reviewed_document_map(config)
    migrations = load_path_migrations(repo_root, config)
    text_extensions = set(config["text_extensions"])
    max_scan = int(config["max_text_scan_bytes"])

    rows: list[dict[str, Any]] = []
    relations: list[Relation] = []
    run_ids_by_path: dict[str, set[str]] = {}
    for path in scoped_paths:
        kind = artifact_kind_for(path)
        size = indexed_size(repo_root, path)
        path_relations, run_ids, truncated, metadata = scan_relations(repo_root, path, text_extensions, max_scan)
        family_id = str(metadata.get("family_id") or family_id_for(path, config))
        status, status_source, canonical_for, status_note = initial_status(path, canonical)
        if path in reviewed:
            review = reviewed[path]
            status = str(review["status"])
            status_source = "reviewed_family_map"
            canonical_for = str(review.get("canonical_for", ""))
            status_note = str(review["reason"])
        metadata_status = str(metadata.get("status", ""))
        if path not in canonical and path not in reviewed and metadata_status in {
            "canonical",
            "supporting",
            "superseded",
            "retracted",
            "draft",
            "temporary",
            "orphan",
        }:
            status = metadata_status
            status_source = "explicit_metadata"
            status_note = "Lifecycle status declared in machine-readable document metadata."
        if path not in canonical and path not in reviewed and metadata.get("canonical_for"):
            canonical_for = str(metadata["canonical_for"])
        relations.extend(path_relations)
        run_ids_by_path[path] = run_ids
        if path not in head_paths:
            git_state = "indexed_not_in_head"
        elif path in staged_paths and path in modified_paths:
            git_state = "staged_and_worktree_modified"
        elif path in staged_paths:
            git_state = "staged"
        elif path in modified_paths:
            git_state = "worktree_modified"
        else:
            git_state = "tracked"
        rows.append(
            {
                "path": path,
                "scope": "docs" if path.startswith("docs/") else "phase_docs",
                "phase": phase_for(path),
                "family_id": family_id,
                "lineage_key": lineage_key_for(path),
                "artifact_kind": kind,
                "document_type": document_type_for(path, kind),
                "extension": PurePosixPath(path).suffix.lower(),
                "bytes": size,
                "git_state": git_state,
                "proposed_storage_class": storage_class_for(path, kind, size),
                "version": str(metadata.get("version") or version_label_for(path, family_id, config)),
                "date": (DATE_RE.search(path).group(1) if DATE_RE.search(path) else ""),
                "proposed_status": status,
                "status_source": status_source,
                "canonical_for": canonical_for,
                "status_note": status_note,
                "run_ids": "",
                "inbound_reference_count": 0,
                "outbound_reference_count": len(path_relations),
                "broken_markdown_reference_count": sum(
                    relation.target_exists == "no" and relation.relation in {"references", "embeds"}
                    for relation in path_relations
                ),
                "git_first_commit": oldest.get(path, ""),
                "git_last_commit": newest.get(path, ""),
                "scan_truncated": "yes" if truncated else "no",
            }
        )

    add_reviewed_relations(repo_root, reviewed, relations)
    add_version_candidates(rows, relations)
    relations = apply_path_migrations(repo_root, relations, migrations)
    inbound = Counter(
        relation.target_path
        for relation in relations
        if relation.target_exists == "yes" and relation.relation in {"references", "embeds", "mentions_path"}
    )
    for row in rows:
        row["inbound_reference_count"] = inbound[row["path"]]
        row["run_ids"] = ";".join(sorted(run_ids_by_path[row["path"]]))
        if (
            row["proposed_status"] == "supporting"
            and row["status_source"] == "default_inventory"
            and row["inbound_reference_count"] == 0
            and row["document_type"] not in {"guide", "manifest_or_receipt"}
            and row["artifact_kind"] != "figure"
        ):
            row["proposed_status"] = "orphan_candidate"
            row["status_source"] = "no_parsed_inbound_reference"
            row["status_note"] = "No parsed inbound path reference was found; human review required."

    relations = sorted(
        set(relations),
        key=lambda item: (item.source_path, item.relation, item.target_path, str(item.line), item.evidence),
    )
    run_rows = build_run_rows(repo_root, config, tracked_paths, head_paths, rows)
    return rows, relations, run_rows


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/repo_inventory.json", help="Path relative to the repository root")
    parser.add_argument("--check", action="store_true", help="Regenerate in memory and fail if committed outputs differ")
    return parser.parse_args(argv)


def generate(
    repo_root: Path,
    config: dict[str, Any],
    output_root: Path | None = None,
) -> dict[str, bytes]:
    rows, relations, run_rows = build_inventory(repo_root, config)
    destination = output_root or repo_root
    outputs = {path: destination / path for path in config["generated_paths"]}

    document_fields = [
        "path",
        "scope",
        "phase",
        "family_id",
        "lineage_key",
        "artifact_kind",
        "document_type",
        "extension",
        "bytes",
        "git_state",
        "proposed_storage_class",
        "version",
        "date",
        "proposed_status",
        "status_source",
        "canonical_for",
        "status_note",
        "run_ids",
        "inbound_reference_count",
        "outbound_reference_count",
        "broken_markdown_reference_count",
        "git_first_commit",
        "git_last_commit",
        "scan_truncated",
    ]
    lineage_fields = ["source_path", "relation", "target_path", "target_exists", "evidence", "confidence", "line"]
    run_fields = [
        "phase",
        "run_id",
        "path",
        "date",
        "git_state",
        "tracked_file_count",
        "tracked_bytes",
        "manifest_count",
        "manifest_paths",
        "version_record_count",
        "version_paths",
        "report_or_index_count",
        "report_or_index_paths",
        "retracted_marker",
        "superseded_marker",
        "linked_document_count",
        "proposed_storage_class",
        "issues",
        "run_root",
    ]

    write_csv(outputs["docs/catalog/DOCUMENT_CATALOG.csv"], document_fields, rows)
    write_csv(
        outputs["docs/catalog/DOCUMENT_LINEAGE.csv"],
        lineage_fields,
        [relation.__dict__ for relation in relations],
    )
    write_csv(outputs["phases/RUN_CATALOG.csv"], run_fields, run_rows)
    write_canonical_map(outputs["docs/catalog/CANONICAL_MAP.md"], rows, run_rows, config)
    write_issues(
        outputs["docs/catalog/CATALOG_ISSUES.md"],
        rows,
        relations,
        run_rows,
        int(config["max_markdown_issue_rows"]),
    )
    return {path: absolute.read_bytes() for path, absolute in outputs.items()}


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = find_repo_root(Path.cwd())
    config_path = (repo_root / args.config).resolve()
    config = load_config(config_path)
    if args.check:
        before = {
            path: (repo_root / path).read_bytes() if (repo_root / path).exists() else None
            for path in config["generated_paths"]
        }
        with tempfile.TemporaryDirectory(prefix="jointbuildgs-repo-inventory-") as temporary:
            after = generate(repo_root, config, Path(temporary))
        changed = [path for path in config["generated_paths"] if before[path] != after[path]]
        if changed:
            print("inventory outputs are stale:", file=sys.stderr)
            for path in changed:
                print(f"  {path}", file=sys.stderr)
            return 1
        print(f"inventory outputs are current ({len(after)} files)")
        return 0
    outputs = generate(repo_root, config)
    for path in config["generated_paths"]:
        print(f"wrote {path} ({len(outputs[path])} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
