"""PHD-REPO-BRANCH-SETUP-v1 3.5: the dry initialisations of the clean checkout against those of PHD-MAIN-PREP-DISCARD-RULE-v1
(jointbuildgs:dev, numpy).

  python compare_runs.py

  /orig         = the discard-rule payload's fork_runs/s52 (read-only)     /orig_checks = its fork_checks (read-only)
  /v            = this task's payload (fork_runs/<tag>, fork_checks/<tag>.json; writes compare/compare_<tag>.json)
  /repo         = this repository (configs/phd/repo_branch_setup_v1/checks_v1.json)
Per run (every box all on, the switch box with each switch off):
  order items  locations.npz state / vote / judgment / unit_judgment, init_points.npz planted, every array of unplanted.npz:
               exact element-wise equality (the order's "patch states, judgments, points not planted")
  recorded     every other array of locations / init_points / unplanted / gate_check.npz (exact, else max |difference| and count),
               bytes of input.ply / cameras.json / faces.csv, E.jsonl / meta.json / init_report.json without keys containing
               'seconds', cfg_args without model_path, the docker command with the moved mounts, the GPU and the name put back
fork_checks    the new fork_checks/<tag>.json against the original fork_checks/s52.json: check 2 of every run, the switch rows of the
               switch box. scientific_verdict: null."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np

C = json.loads(Path("/repo/configs/phd/repo_branch_setup_v1/checks_v1.json").read_text())
TAG = C["tag"]
ORIG, NEW = Path("/orig"), Path("/v/fork_runs") / TAG
ORDER = C["compare"]["order_items_exact"]
NPZ = ("locations.npz", "init_points.npz", "unplanted.npz", "gate_check.npz")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def strip(o):
    """JSON without keys containing 'seconds' and with the model path of either run replaced."""
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if "seconds" not in k}
    if isinstance(o, list):
        return [strip(v) for v in o]
    if isinstance(o, str):
        return re.sub(r"/pv?/fork_runs/[^/]+/[^/]+/model", "<model>", o)
    return o


def json_paths_differing(a, b, pfx="", out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            json_paths_differing(a.get(k), b.get(k), f"{pfx}.{k}" if pfx else k, out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            json_paths_differing(x, y, f"{pfx}[{i}]", out)
    elif a != b:
        out.append(pfx)
    return out


def load_json_lines(p):
    return [strip(json.loads(x)) for x in p.read_text().splitlines() if x.strip()] if p.exists() else None


def cmd_norm(cmd, name):
    """the moved mounts, the model path, the container name and the GPU put back to one form."""
    out, i = [], 0
    while i < len(cmd):
        a = cmd[i]
        if a == "-v" and (cmd[i + 1].endswith(":/pv")):
            i += 2; continue
        if a == "-v" and (cmd[i + 1].endswith(":/p") or cmd[i + 1].endswith(":/p:ro")):
            out += ["-v", "<discard-rule payload>:/p"]; i += 2; continue
        if a == "-v" and cmd[i + 1].endswith(":/source:ro"):
            out += ["-v", "<r11>:/source:ro"]; i += 2; continue
        if a in ("--name", "--gpus", "-m"):
            out += [a, "<varies>"]; i += 2; continue
        out.append(a); i += 1
    return out


def compare_arrays(fa, fb, order_keys):
    a, b = np.load(fa), np.load(fb)
    ka, kb = set(a.files), set(b.files)
    rows, order_ok = {}, True
    for k in sorted(ka | kb):
        if k not in ka or k not in kb:
            rows[k] = dict(missing_in="original" if k not in ka else "new"); order_ok &= k not in order_keys; continue
        x, y = a[k], b[k]
        same = x.shape == y.shape and x.dtype == y.dtype and bool(
            np.array_equal(x, y, equal_nan=x.dtype.kind in "fc"))
        r = dict(equal=same)
        if not same and x.shape == y.shape and x.dtype.kind in "fciub" and y.dtype.kind in "fciub":
            d = np.abs(x.astype(np.float64) - y.astype(np.float64))
            m = ~(np.isnan(x.astype(np.float64)) & np.isnan(y.astype(np.float64)))
            r.update(n_differing=int(((d > 0) | (np.isnan(d) & m))[m].sum()), max_abs_difference=float(np.nanmax(d)) if d.size else 0.0)
        elif not same:
            r.update(shapes=[list(x.shape), list(y.shape)], dtypes=[x.dtype.str, y.dtype.str])
        rows[k] = r
        if k in order_keys:
            order_ok &= same
    return rows, order_ok


def one(name):
    o, n = ORIG / name, NEW / name
    res = dict(run=name)
    ro, rn = json.loads((o / "receipt.json").read_text()), json.loads((n / "receipt.json").read_text())
    res["status"] = [ro["status"], rn["status"]]; res["gpu"] = [ro["gpu"], rn["gpu"]]; res["seconds"] = [ro["seconds"], rn["seconds"]]
    res["command_equal_after_moved_mounts"] = cmd_norm(ro["command"], name) == cmd_norm(rn["command"], name)
    mo, mn = o / "model/monitor", n / "model/monitor"
    order_all = True
    res["arrays"] = {}
    for f in NPZ:
        keys = ORDER.get(f, [])
        if f == "unplanted.npz" and (mo / f).exists():
            keys = list(np.load(mo / f).files)
        if not (mo / f).exists() or not (mn / f).exists():
            present = [(mo / f).exists(), (mn / f).exists()]
            res["arrays"][f] = dict(present=present, all_equal=not any(present))
            order_all &= not any(present) or not keys; continue
        rows, ok = compare_arrays(mo / f, mn / f, keys)
        res["arrays"][f] = dict(all_equal=all(r.get("equal", False) for r in rows.values()), order_items=keys,
                                order_items_equal=ok, differing={k: r for k, r in rows.items() if not r.get("equal", False)})
        order_all &= ok
    res["order_items_equal"] = bool(order_all)
    res["bytes_equal"] = {f: sha(o / "model" / f) == sha(n / "model" / f) for f in ("input.ply", "cameras.json")}
    res["bytes_equal"]["faces.csv"] = sha(mo / "faces.csv") == sha(mn / "faces.csv")
    for f in ("E.jsonl", "scalars.jsonl"):
        res["bytes_equal"][f + " (without *seconds*)"] = load_json_lines(mo / f) == load_json_lines(mn / f)
    for f in ("meta.json", "init_report.json"):
        a, b = strip(json.loads((mo / f).read_text())), strip(json.loads((mn / f).read_text()))
        dp = json_paths_differing(a, b)
        res["bytes_equal"][f + " (without *seconds*)"] = not dp
        if dp:
            res.setdefault("json_paths_differing", {})[f] = dp[:30]
    ca = re.sub(r"model_path='[^']*'", "model_path=<model>", (o / "model/cfg_args").read_text())
    cb = re.sub(r"model_path='[^']*'", "model_path=<model>", (n / "model/cfg_args").read_text())
    res["bytes_equal"]["cfg_args (without model_path)"] = ca == cb
    res["everything_compared_equal"] = bool(order_all and res["command_equal_after_moved_mounts"] and all(res["bytes_equal"].values())
                                            and all(v.get("all_equal", True) for v in res["arrays"].values()))
    return res


def main():
    runs = [f"{b}_{p}" for b in C["boxes"] for p in C["priors"]]
    runs += [f"{C['switch_box']}_{p}_sw-{s}" for p in C["priors"] for s in C["switches"]]
    out = dict(tag=TAG, original_tag=C["originals"]["fork_runs_tag"], runs={})
    for r in runs:
        out["runs"][r] = one(r)
        x = out["runs"][r]
        print(r, "order items equal" if x["order_items_equal"] else "ORDER ITEMS DIFFER",
              "| everything equal" if x["everything_compared_equal"] else "| other differences recorded", flush=True)
    fo = json.loads(Path("/orig_checks/s52.json").read_text())
    fn = json.loads((Path("/v/fork_checks") / f"{TAG}.json").read_text())
    c2 = {k: fo["check2"][k] == fn["check2"].get(k) for k in fo["check2"]}
    sw = {s: {k: fo["switches"][s][k] == fn["switches"][s].get(k) for k in fo["switches"][s] if k.startswith(C["switch_box"] + "_")}
          for s in C["switches"]}
    out["fork_checks"] = dict(
        new_check2_all_equal=fn["check2_all_equal"],
        new_check2=dict((k, v.get("equal")) for k, v in fn["check2"].items()),
        check2_rows_equal_original=c2,
        switch_rows_equal_original=sw,
        new_unexpected_switch_changes={s: {k: v for k, v in d.items() if k.startswith(C["switch_box"] + "_")}
                                       for s, d in fn["switches_unexpected"].items()},
        other_boxes_switch_runs="not re-run (only switch_box); fork_checks.py marks them missing")
    out["summary"] = dict(
        runs=len(runs), order_items_equal=sum(x["order_items_equal"] for x in out["runs"].values()),
        everything_compared_equal=sum(x["everything_compared_equal"] for x in out["runs"].values()),
        check2_all_equal=bool(fn["check2_all_equal"]), check2_rows_equal_original=all(c2.values()),
        switch_rows_equal_original=all(all(d.values()) for d in sw.values()),
        unexpected_switch_changes=sum(len(v) for v in out["fork_checks"]["new_unexpected_switch_changes"].values()))
    out["scientific_verdict"] = None
    Path("/v/compare").mkdir(exist_ok=True)
    Path(f"/v/compare/compare_{TAG}.json").write_text(json.dumps(out, indent=1, default=str))
    print("SUMMARY", json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
