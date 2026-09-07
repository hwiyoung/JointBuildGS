#!/usr/bin/env python3
"""Bounded official GeoGS example download and archive-only provenance inspection.

Uses Python's standard library. Does not extract data, import project dependencies,
run downloaded code, or read image/depth/reference payloads. Public Google Drive
confirmation forms are followed using their published hidden form fields.
"""

import argparse
import datetime as dt
import hashlib
import html.parser
import http.cookiejar
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import struct
import sys
import time
import urllib.parse
import urllib.request
import zipfile


DEFAULT_URL = "https://drive.google.com/uc?export=download&id=1QPp349lFSuBiyfcJBbcG3eIweiVt_Etp"
UPSTREAM_COMMIT = "db40c95c657ec03ff21c83cb99cf39f4e90247a6"
MAX_BYTES = 2_000_000_000
MAX_SECONDS = 300
MAX_TEXT_BYTES = 262_144
MAX_CAMERA_BYTES = 8_000_000


class PublicDownloadForm(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""),
                            "method": attrs.get("method", "get").lower(), "fields": []}
        elif tag == "input" and self.current is not None and attrs.get("name"):
            self.current["fields"].append((attrs["name"], attrs.get("value", "")))

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("The complete download/inspection deadline was reached")
    return value


def checked_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "drive.google.com", "drive.usercontent.google.com", "docs.google.com"
    }:
        raise ValueError("Unexpected public download confirmation destination")
    return url


def download(output, url, max_bytes, deadline, receipt):
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request(checked_url(url), headers={"User-Agent": "GeoGS-example-provenance/1.0"})
    partial = output / "example_scene.zip.part"
    digest = hashlib.sha256()
    received = 0
    for attempt in range(4):
        with opener.open(request, timeout=min(20, remaining(deadline))) as response:
            final_url = response.geturl()
            info = {"attempt": attempt + 1, "status": response.status,
                    "url": final_url, "content_type": response.headers.get("Content-Type"),
                    "content_length": response.headers.get("Content-Length"),
                    "content_disposition": response.headers.get("Content-Disposition")}
            receipt["http_responses"].append(info)
            content_type = (info["content_type"] or "").lower()
            first = response.read(4096)
            remaining(deadline)
            if "text/html" in content_type or first.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                page = first + response.read(1_000_000)
                parser = PublicDownloadForm()
                parser.feed(page.decode("utf-8", errors="replace"))
                forms = [form for form in parser.forms if "download" in form["action"]]
                info["html_sha256"] = sha256_bytes(page)
                info["html_bytes_inspected"] = len(page)
                info["public_confirmation_form_count"] = len(forms)
                if not forms:
                    raise RuntimeError("HTML response contains no public download confirmation form")
                form = forms[0]
                action = checked_url(urllib.parse.urljoin(final_url, form["action"]))
                info["confirmation_action"] = action
                info["confirmation_field_names"] = [name for name, _ in form["fields"]]
                encoded = urllib.parse.urlencode(form["fields"])
                if form["method"] == "get":
                    action += ("&" if "?" in action else "?") + encoded
                    data = None
                elif form["method"] == "post":
                    data = encoded.encode("ascii")
                else:
                    raise ValueError("Unsupported public confirmation form method")
                request = urllib.request.Request(action, data=data,
                    headers={"User-Agent": "GeoGS-example-provenance/1.0"})
                print("Following the public Google Drive download confirmation form", flush=True)
                continue
            if first[:4] != b"PK\x03\x04":
                raise ValueError("Download response is not a ZIP archive")
            if info["content_length"] and int(info["content_length"]) > max_bytes:
                raise ValueError("Advertised archive size exceeds the authorized byte limit")
            receipt["download_final_url"] = final_url
            expected_size = int(info["content_length"]) if info["content_length"] else None
            with partial.open("xb") as handle:
                chunk = first
                last_report = time.monotonic()
                while chunk:
                    remaining(deadline)
                    if received + len(chunk) > max_bytes:
                        raise ValueError("Downloaded bytes exceed the authorized byte limit")
                    handle.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    receipt["download_bytes"] = received
                    receipt["download_sha256"] = digest.hexdigest()
                    if time.monotonic() - last_report >= 15:
                        print(f"Downloaded {received / 1_000_000:.1f} MB", flush=True)
                        last_report = time.monotonic()
                    chunk = response.read(1024 * 1024)
            if expected_size is not None and received != expected_size:
                raise ValueError("Received size does not match HTTP Content-Length")
            completed = output / "example_scene.zip"
            partial.rename(completed)
            receipt["archive_path"] = completed.name
            receipt["content_length_matches"] = expected_size == received if expected_size is not None else None
            return completed
    raise RuntimeError("Public confirmation retry limit reached")


def camera_binary_summary(data, basename):
    stream = io.BytesIO(data)
    count, = struct.unpack("<Q", stream.read(8))
    result = {"record_count": count}
    if count > 100_000:
        raise ValueError("Unreasonable camera metadata record count")
    if basename == "images.bin":
        images = []
        for _ in range(count):
            packed = stream.read(64)
            values = struct.unpack("<i7di", packed)
            name = bytearray()
            while True:
                char = stream.read(1)
                if not char or len(name) > 4096:
                    raise ValueError("Invalid COLMAP image name")
                if char == b"\0":
                    break
                name.extend(char)
            point_count, = struct.unpack("<Q", stream.read(8))
            if stream.tell() + point_count * 24 > len(data):
                raise ValueError("Truncated COLMAP image observations")
            stream.seek(point_count * 24, io.SEEK_CUR)
            images.append({"id": values[0], "name": name.decode("utf-8"),
                           "camera_id": values[-1], "qvec": list(values[1:5]),
                           "tvec": list(values[5:8]), "point2d_count": point_count})
        result["images"] = images
        ordered = sorted(images, key=lambda item: item["name"].split("/")[-1].split(".")[0])
        result["derived_upstream_default_split"] = {
            "status": "DERIVED_FROM_UPSTREAM_EVAL_TRUE_LLFFHOLD_8_NOT_AUTHOR_RUN_RECEIPT",
            "train": [item["name"] for i, item in enumerate(ordered) if i % 8 != 0],
            "test": [item["name"] for i, item in enumerate(ordered) if i % 8 == 0],
            "source": f"https://github.com/zqlin0521/GeoGS/blob/{UPSTREAM_COMMIT}/scene/dataset_readers.py#L372"}
    return result


def category(name):
    path = PurePosixPath(name)
    parts = [part.lower() for part in path.parts]
    lower = name.lower()
    leaf = path.name.lower()
    if "images" in parts and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return "rgb_images"
    if "raw_depth" in parts and leaf.endswith(".npy"):
        if "lod" in lower:
            return "lod_structural_depth"
        if "da3" in lower or "da_prior" in lower:
            return "da3_visual_depth"
        return "other_depth"
    if "ground_truth" in parts or "gt" in parts:
        return "evaluation_reference"
    if leaf == "lod2_pcd.ply":
        return "lod2_protection_pointcloud"
    if leaf in {"cameras.bin", "images.bin", "cameras.txt", "images.txt"}:
        return "camera_metadata"
    if leaf in {"points3d.bin", "points3d.txt", "points3d.ply"}:
        return "initial_pointcloud"
    if path.suffix.lower() in {".json", ".yaml", ".yml", ".toml", ".ini", ".md", ".sh"} or leaf in {"cfg_args", "args.txt", "config.txt"}:
        return "configuration_or_documentation"
    return "other"


def inspect_archive(archive_path, output, receipt, deadline):
    members = []
    inputs = {}
    inspected = []
    camera_records = []
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > 100_000:
            raise ValueError("Archive has too many entries for bounded metadata inspection")
        for info in infos:
            remaining(deadline)
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive member path")
            kind = category(info.filename)
            record = {"path": info.filename, "bytes": info.file_size,
                      "compressed_bytes": info.compress_size, "crc32": f"{info.CRC:08x}", "category": kind}
            members.append(record)
            inputs.setdefault(kind, []).append(info.filename)
        write_json(output / "archive_members.json", members)
        for record in members:
            remaining(deadline)
            name = record["path"]
            basename = PurePosixPath(name).name.lower()
            is_camera = record["category"] == "camera_metadata"
            is_text = record["category"] == "configuration_or_documentation" or (is_camera and basename.endswith(".txt"))
            limit = MAX_TEXT_BYTES if is_text else MAX_CAMERA_BYTES
            if not (is_camera or is_text) or record["bytes"] > limit:
                continue
            data = archive.read(name)
            entry = {"path": name, "bytes": len(data), "sha256": sha256_bytes(data)}
            try:
                if is_text:
                    entry["text"] = data.decode("utf-8")
                elif basename in {"images.bin", "cameras.bin"}:
                    entry["colmap"] = camera_binary_summary(data, basename)
                    camera_records.append({"path": name, **entry["colmap"]})
            except Exception as error:
                entry["inspection_error"] = f"{type(error).__name__}: {error}"
            inspected.append(entry)
        write_json(output / "small_metadata_inspection.json", inspected)
    manifest = {
        "input_files_by_type": inputs,
        "counts_by_type": {key: len(value) for key, value in inputs.items()},
        "camera_records": camera_records,
        "depth_and_rgb_stems": {key: sorted(PurePosixPath(name).stem for name in inputs.get(key, []))
                                for key in ("rgb_images", "lod_structural_depth", "da3_visual_depth")},
        "parameter_provenance_files": inputs.get("configuration_or_documentation", []),
        "upstream_default_invocation_source": f"https://github.com/zqlin0521/GeoGS/blob/{UPSTREAM_COMMIT}/scripts/run_example.sh",
        "author_actual_training_run_parameters_verified": False,
        "inspection_scope": "ZIP directory plus bounded configuration/text/camera metadata only; no image, depth, pointcloud or evaluation-reference arrays read",
        "archive_extracted": False,
        "training_or_inference_executed": False,
        "scientific_verdict": None}
    write_json(output / "input_manifest.json", manifest)
    receipt["member_count"] = len(members)
    receipt["uncompressed_total_bytes"] = sum(record["bytes"] for record in members)
    receipt["input_counts"] = manifest["counts_by_type"]
    receipt["inspected_metadata_count"] = len(inspected)
    receipt["archive_crc_check_scope"] = "Inspected small members only; no full payload decompression or CRC test"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--timeout-seconds", type=int, default=MAX_SECONDS)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    if not 0 < args.max_bytes <= MAX_BYTES or not 0 < args.timeout_seconds <= MAX_SECONDS:
        parser.error("Limits may only be reduced from 2 GB and 300 seconds")
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("receipt.json", "example_scene.zip", "example_scene.zip.part", "archive_members.json", "input_manifest.json", "small_metadata_inspection.json"):
        if (args.output / name).exists():
            parser.error(f"Refusing to overwrite existing artifact: {name}")
    started = time.monotonic()
    receipt = {
        "task_id": "PHD-GEOGS-CONTRIBUTION-v1-OFFICIAL-EXAMPLE-INSPECTION",
        "status": "STARTED", "source_url": args.url, "upstream_commit": UPSTREAM_COMMIT,
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "maximum_download_bytes": args.max_bytes, "maximum_elapsed_seconds": args.timeout_seconds,
        "python": platform.python_version(), "container_image_id": args.image_id,
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "command_argv": sys.argv, "http_responses": [], "download_bytes": 0,
        "sha256_scope": "Locally computed download identity; author-published checksum not provided",
        "archive_extracted": False, "training_or_inference_executed": False,
        "scientific_verdict": None}
    code = 0
    try:
        deadline = started + args.timeout_seconds
        archive = download(args.output, args.url, args.max_bytes, deadline, receipt)
        inspect_archive(archive, args.output, receipt, deadline)
        receipt["status"] = "OFFICIAL_EXAMPLE_DOWNLOADED_AND_METADATA_INSPECTED"
    except Exception as error:
        receipt["status"] = "OFFICIAL_EXAMPLE_DOWNLOAD_OR_INSPECTION_FAILED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        code = 1
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        receipt["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(args.output / "receipt.json", receipt)
        print(json.dumps({key: receipt.get(key) for key in ("status", "download_bytes", "input_counts", "elapsed_seconds", "error")}, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
