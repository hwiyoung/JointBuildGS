"""PHD-CH6-FACTS64-v1: copies of the evidence named in the facts table (order section 4: 'the config files and report sections
used as evidence'), for the document session, which has no access to this server. (jointbuildgs:dev, CPU, standard library)
  python copy_evidence.py
Reads the evidence cells of /out/final/facts_6_4.json (and its section extras and appendix) and, for every backticked path:
  - configs/** and docs/**/*.md (and docs-relative 'main_.../x.md', bare report names): the whole file;
  - payload text records (json, md, csv, txt, log, cfg; short names PREP, DR, S0-S3, FX, SB, SL, GG, MT, CH6, F64, P0): the whole
    file up to 2 MB, else the cited line ranges;
  - code (scripts/, src/, tests/, phases/, Dockerfile*): the cited line ranges with 2 lines around (whole file when no range is cited
    and it is under 60 kB);
  - skipped and listed with the reason: paths with placeholders (<...>, *, {...}), binary files, missing files, directories.
Writes /out/evidence/files/<repo|payload>/... and /out/final/근거_목록.md (cited path, copy, kind, sha256 of the source, size).
scientific_verdict: null."""
import hashlib
import json
import re
import shutil
from pathlib import Path

OUT = Path("/out"); REPO = Path("/repo"); ART = Path("/art/phase-payloads")
E = OUT / "evidence/files"
PAYLOAD = {"PREP": "phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1", "DR": "phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1",
           "S0": "phd/main_stage0_v1/PHD-MAIN-STAGE0-v1", "S1": "phd/main_stage1_v1/PHD-MAIN-STAGE1-v1",
           "S2": "phd/main_stage2_v1/PHD-MAIN-STAGE2-v1", "S3": "phd/main_stage3_v1/PHD-MAIN-STAGE3-v1", "FX": "phd/main_fix_v1/PHD-MAIN-FIX-v1",
           "SB": "phd/main_baselines_v1/PHD-MAIN-BASELINES-v1", "SL": "phd/main_fill_v1/PHD-MAIN-FILL-v1",
           "GG": "phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1", "MT": "phd/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1",
           "CH6": "phd/ch6_support_v1/PHD-CH6-SUPPORT-v1", "F64": "phd/ch6_facts64_v1/PHD-CH6-FACTS64-v1", "P0": "p0-audit"}
TEXT = {".json", ".md", ".csv", ".txt", ".log", ".cfg", ".yaml", ".yml", ".sh", ".py", ".diff", ".ini", ".toml"}
CODE_ROOTS = ("scripts/", "src/", "tests/", "phases/")
TOKEN = re.compile(r"`([^`]+)`(:[0-9][0-9,\- ]*)?")
RANGE = re.compile(r"(\d+)(?:\s*-\s*(\d+))?")
DOCS = REPO / "docs/experiments/phd"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:12]


def resolve(path):
    """(source file, copy name under files/) or (None, reason)."""
    if any(c in path for c in "<*{…") or path.endswith("/"):
        return None, "자리표나 폴더"
    first = path.split("/", 1)[0]
    if first in PAYLOAD and "/" in path:
        return ART / PAYLOAD[first] / path.split("/", 1)[1], f"payload/{path}"
    if path.startswith(("docs/", "configs/", "artifacts/") + CODE_ROOTS) or path.startswith("Dockerfile"):
        return REPO / path, f"repo/{path}"
    if "/" in path and (DOCS / first).is_dir():
        return DOCS / path, f"repo/docs/experiments/phd/{path}"
    if "/" not in path and path.endswith((".md", ".json")):      # a bare report or config name: the one file of that name
        hits = sorted(DOCS.glob(f"**/{path}")) + sorted((REPO / "configs/phd").glob(f"**/{path}"))
        if len(hits) == 1:
            return hits[0], f"repo/{hits[0].relative_to(REPO)}"
        return None, f"이름만 있고 찾은 파일 {len(hits)}개"
    if path.startswith("stage1/") and (ART / PAYLOAD["S1"] / path).exists():   # agent A: a stage-1 receipt named from S1
        return ART / PAYLOAD["S1"] / path, f"payload/S1/{path}"
    return None, "경로가 아님(명령, 값, 이름)"


def ranges(txt):
    out = []
    for a, b in RANGE.findall(txt or ""):
        a = int(a); b = int(b) if b else a
        if 0 < a <= b and b - a < 400:
            out.append((a, b))
    return out


def excerpt(src, rngs, ctx):
    L = src.read_text(errors="replace").splitlines()
    keep = sorted({k for a, b in rngs for k in range(max(1, a - ctx), min(len(L), b + ctx) + 1)})
    out, prev = [], None
    for k in keep:
        if prev is not None and k != prev + 1:
            out.append("   ...")
        out.append(f"{k:6d}  {L[k - 1]}"); prev = k
    return "\n".join(out) + "\n"


def main():
    J = json.loads((OUT / "final/facts_6_4.json").read_text())
    cites = []                                         # (row, path, line text)
    for r in J["rows"]:
        prev = None                                    # a short path is first read relative to the folders of the cell's previous path
        for m in TOKEN.finditer(r["evidence"]):
            tok, after = m.group(1), m.group(2) or ""
            path = re.split(r"[:(\s]", tok, 1)[0].rstrip(",;")
            rest = tok[len(path):] + " " + after
            src, _ = resolve(path)
            if (src is None or not src.exists()) and prev and not any(c in path for c in "<*{…"):
                base = prev
                while "/" in base:
                    base = base.rsplit("/", 1)[0]
                    s2, _ = resolve(base + "/" + path)
                    if s2 is not None and s2.exists() and s2.is_file():
                        path = base + "/" + path; break
            if resolve(path)[0] is not None:
                prev = path
            cites.append((r["no"], path, rest))
    full = {}                                          # basename -> the full cited paths that exist (for names cited alone)
    for _, path, _ in cites:
        src, _ = resolve(path)
        if src is not None and src.exists() and src.is_file():
            full.setdefault(Path(path).name, set()).add(path)
    cites = [(no, (next(iter(full[path])) if "/" not in path and len(full.get(path, ())) == 1 else path), rest)
             for no, path, rest in cites]
    for sid, blk in J["section_extra_md"].items():
        for m in TOKEN.finditer(blk):
            path = re.split(r"[:(\s]", m.group(1), 1)[0]
            cites.append((f"{sid} 표", path, m.group(1)[len(path):] + " " + (m.group(2) or "")))
    by = {}
    for no, path, rest in cites:
        d = by.setdefault(path, dict(rows=[], ranges=[]))
        d["rows"].append(no); d["ranges"] += ranges(rest.split("(")[0] if path.endswith((".py", ".sh", ".log")) else rest)
    if E.exists():
        shutil.rmtree(E)
    E.mkdir(parents=True)
    rows = []
    for path, d in sorted(by.items()):
        src, name = resolve(path)
        rec = dict(path=path, rows=sorted(set(d["rows"])))
        if src is None:
            rec.update(kind="건너뜀", why=name); rows.append(rec); continue
        if not src.exists():
            rec.update(kind="건너뜀", why="파일이 없음"); rows.append(rec); continue
        if src.is_dir():
            rec.update(kind="건너뜀", why="폴더"); rows.append(rec); continue
        size = src.stat().st_size; rec.update(sha256=sha(src), size=size)
        dst = E / name; dst.parent.mkdir(parents=True, exist_ok=True)
        suffix = src.suffix.lower(); is_code = name.startswith(tuple("repo/" + c for c in CODE_ROOTS)) or src.name.startswith("Dockerfile")
        if suffix not in TEXT and not src.name.startswith("Dockerfile"):
            rec.update(kind="건너뜀", why=f"이진 파일({suffix or '확장자 없음'})"); rows.append(rec); continue
        if is_code:
            if d["ranges"]:
                dst = dst.with_name(dst.name + ".excerpt.txt"); dst.write_text(f"# {path} (인용한 줄과 둘레 2줄, sha256 {rec['sha256']})\n" + excerpt(src, d["ranges"], 2))
                rec.update(kind="발췌", copy=str(dst.relative_to(OUT)))
            elif size < 60_000:
                shutil.copy2(src, dst); rec.update(kind="전체", copy=str(dst.relative_to(OUT)))
            else:
                rec.update(kind="건너뜀", why="큰 코드 파일이고 인용한 줄이 없음")
        elif size <= 2_000_000:
            shutil.copy2(src, dst); rec.update(kind="전체", copy=str(dst.relative_to(OUT)))
        elif d["ranges"]:
            dst = dst.with_name(dst.name + ".excerpt.txt"); dst.write_text(f"# {path} (인용한 줄과 둘레 2줄, sha256 {rec['sha256']})\n" + excerpt(src, d["ranges"], 2))
            rec.update(kind="발췌", copy=str(dst.relative_to(OUT)))
        else:
            rec.update(kind="건너뜀", why=f"큰 기록({size / 1e6:.1f} MB)이고 인용한 줄이 없음")
        rows.append(rec)
    n = {k: sum(r["kind"] == k for r in rows) for k in ("전체", "발췌", "건너뜀")}
    L = ["<!-- PHD-CH6-FACTS64-v1 근거 목록 -->", "# 근거 목록 (사실표 facts_6_4.md의 근거 칸)", "",
         f"- 근거 칸이 이름 붙인 경로 {len(rows)}개: 통째로 복사 {n['전체']}, 인용한 줄만 발췌 {n['발췌']}, 건너뜀 {n['건너뜀']}.",
         "- 사본은 전달 묶음의 `evidence/files/`에 있다(`repo/` = 저장소, `payload/<줄임>/` = 페이로드). sha256은 원본의 앞 12자리다.",
         "- 설정과 보고서는 통째로, 코드와 큰 기록은 인용한 줄과 그 둘레 2줄을 옮겼다. 자리표가 든 경로(`<지역>` 등)는 여러 파일을 뜻해 건너뛰었다. "
         "그 가운데 하나를 보려면 같은 폴더의 다른 이름으로 바꿔 원본에서 읽는다.",
         "- 에이전트가 따로 적은 근거 목록(경로와 줄 범위, 메모)은 `drafts/<A|B|C>/evidence_<A|B|C>.txt`다.", "",
         "| 근거 경로 | 쓴 줄 | 사본 | 방식 | sha256 | 크기 |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| `{r['path']}` | {', '.join(r['rows'][:6])}{' 외' if len(r['rows']) > 6 else ''} | "
                 f"{'`' + r['copy'] + '`' if r.get('copy') else '—'} | {r['kind']}{' (' + r['why'] + ')' if r.get('why') else ''} | "
                 f"{r.get('sha256', '—')} | {format(r['size'], ',') if r.get('size') is not None else '—'} |")
    (OUT / "final/근거_목록.md").write_text("\n".join(L) + "\n")
    (OUT / "final/evidence_index.json").write_text(json.dumps(dict(counts=n, rows=rows, scientific_verdict=None), ensure_ascii=False, indent=1))
    print(n, "paths", len(rows))


if __name__ == "__main__":
    main()
