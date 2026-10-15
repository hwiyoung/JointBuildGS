"""PHD-CH6-FACTS64-v1: the facts table facts_6_4.md and facts_6_4.json, assembled from the four writers' drafts
(agents/A: tasks 1, 6 and appendix D; agents/B: tasks 2 and 3.1-3.4; agents/C: tasks 4 and 5; agents/M, the main session:
task 3.5 and task 8) in the order's section order 2.1-2.6, 2.8, then appendix D (order section 3). Text only (no data):
  - the rows are copied as the writers wrote them, with one path vocabulary: the prefixes 'REPO/' and '저장소/' are dropped
    (repo-relative paths) and payload folders get the short names of PAYLOAD below;
  - a row number column is added (<section>-<n>, numbered through the section);
  - the main session's status changes after re-checking the sources are applied (FIXES below, each with its reason in the row);
  - the head (title, notes, summary) and the tail (Figure 6.1 note, run record) are the main session's text: facts_head.md and
    facts_tail.md next to this file. The summary's row references are checked against the assembled rows.
(jointbuildgs:dev, CPU, standard library only)
  python assemble_facts.py [--list]      --list: print the assembled rows (number, writer, status, fact) and stop
Writes /out/final/facts_6_4.md and /out/final/facts_6_4.json. scientific_verdict: null."""
import json
import re
import sys
from pathlib import Path

OUT = Path("/out"); AG = OUT / "agents"; HERE = Path(__file__).resolve().parent
PAYLOAD = {"main_prep_measure_v1": "PREP", "main_prep_discard_rule_v1": "DR", "main_stage0_v1": "S0", "main_stage1_v1": "S1",
           "main_stage2_v1": "S2", "main_stage3_v1": "S3", "main_fix_v1": "FX", "main_baselines_v1": "SB", "main_fill_v1": "SL",
           "geogs_p1p2p3_v1": "GG", "metrics_trial_v1": "MT", "ch6_support_v1": "CH6", "ch6_facts64_v1": "F64"}
SRC = {"A": AG / "A/facts_A.md", "B": AG / "B/facts_B.md", "C": AG / "C/facts_C.md", "M": AG / "M/facts_M.md"}
# (section id, title, note lines, [(writer, source heading, subsection title or None)])
SECTIONS = [
    ("2.1", "본 방법 (일 1)", [], [("A", "## 일 1. 본 방법", None)]),
    ("2.2", "MVS와 관측 신뢰도 마스크 (일 2)", [],
     [("B", "### 2-가. MVS", "가. MVS"), ("B", "### 2-나. 마스크 규칙과 세 기준", "나. 마스크 규칙과 세 기준"),
      ("B", "### 2-다. 마스크 기록", "다. 마스크 기록")]),
    ("2.3", "허용 오차와 정합 (일 3)", [],
     [("B", "### 3.1 실제로 쓴 값과 탐색 지역을 고른 규칙", "가. 실제로 쓴 값과 탐색 지역을 고른 규칙 (찾을 것 1)"),
      ("B", "### 3.2 표본 수와 걸러 낸 몫", "나. 표본 수와 걸러 낸 몫 (찾을 것 2)"),
      ("B", "### 3.3 기관 정확도와 경고 기록", "다. 기관 정확도와 경고 기록 (찾을 것 3)"),
      ("B", "### 3.4 비교 방법이 받은 사전 정보의 정합", "라. 비교 방법이 받은 사전 정보의 정합 (찾을 것 4)"),
      ("M", "## 2.3의 5번", "마. 항공 LiDAR가 τ의 1~2배 어긋난 넓이 (찾을 것 5)")]),
    ("2.4", "충돌 문턱 배수의 준비 측정 (일 4)",
     ["- 이 절의 줄임: '보고서' = `main_prep_discard_rule_v1/버리는기준_보고서_v1.md`(둘째 준비 측정), '결정요청' = "
      "`main_prep_discard_rule_v1/버리는기준_결정요청_v1.md`. '지지 패치' = 영상이 확인한 패치, '결측 패치' = 찍혔지만 영상이 확인하지 못한 "
      "패치, '잘못 버림' = 맞는 사전 정보를 버림, '잘못 지킴' = 틀린 사전 정보를 지킴."],
     [("C", "## 1. 항목 4 — 충돌 문턱의 배율을 고른 준비 측정", None)]),
    ("2.5", "비교 방법 (일 5)",
     ["- 이 절의 줄임: '보고서' = `main_baselines_v1/본실험_비교방법_보고서_v1.md`, '발주문 v1.1' = "
      "`main_baselines_v1/본실험_비교방법_발주문_v1.1.md`, '준비보고' = `main_baselines_v1/본실험_비교방법_준비보고_v1.md`, "
      "'채우기 발주문' = `main_fill_v1/본실험_채우기_발주문_v1.md`."],
     [("C", "### 2.1 2차원 가우시안 스플래팅", "가. 2차원 가우시안 스플래팅"), ("C", "### 2.2 GeoGS", "나. GeoGS"),
      ("C", "### 2.3 MVS 기반 결합 (Zhou 외 2020의 재현)", "다. MVS 기반 결합 (Zhou 외 2020의 재현)"),
      ("C", "### 2.4 CDGS", "라. CDGS"), ("C", "### 2.5 학습 전 사전 정보 (기준)", "마. 학습 전 사전 정보 (기준)")]),
    ("2.6", "모든 방법에 같은 조건 (일 6)", [], [("A", "## 일 6. 모든 방법에 같은 조건", None)]),
    ("2.8", "B0 대상 건물의 벽 참값 (일 8)",
     ["- 발주문 2.8의 4번(GeoGS 저자가 B0 참값을 만든 방식)은 발주문대로 기다리지 않았다. 실험 서버에는 GeoGS 논문 PDF가 없다."],
     [("M", "## 2.8 B0 대상 건물의 벽 참값", None)]),
    ("D", "부록 D의 값과 코드 (발주 3절)", [], [("A", "## 3절. 부록 D의 값과 코드", None)]),
]
# extra blocks copied verbatim after a section's table: (section id, writer, first line prefix, stop at a line starting with)
EXTRA = [("2.4", "C", "**표 4-가.", "## ")]
TAIL_BLOCKS = {"{{A_TIMES}}": ("A", "## 학습 시간 표")}
RECHECK = "실행 세션이 네 상자의 겹침을 다시 세어 같음을 확인(파일 이름 줄기로 맞춤)"
# main-session status changes: (writer, start of the fact cell) -> new status, text added to the value, text added to the method
FIXES = {
    ("C", "6장 보조 작업이 말한 '준비 측정 2.5'"): dict(
        status="다름 (배수를 고른 측정과 다른 보고서)",
        value=" 발주문 2.4의 '같은 보고서로 보인다'와 다르다: 배수를 고른 것은 둘째 준비 측정(버리는 기준, 10월 5일)이고, 6장 보조 작업이 "
              "가리킨 '준비 측정 2.5'는 첫째 준비 측정(10월 2~4일)의 2.5절 '전제가 어긋날 때'다(실행 세션이 두 문서의 절 제목으로 확인)."),
    ("C", "고친 판의 두 고침"): dict(
        status="다름 (DA3 묶음 축척 고침은 B173 주변만)",
        value=" 발주문의 '고친 판(가림 검사, DA3 깊이 묶음의 축척)'은 두 고침이 모든 지역에 든 것처럼 읽힌다. 가림 검사 고침은 네 지역 모두, "
              "DA3 묶음 축척 고침은 B173 주변뿐이다."),
    ("C", "항공 LiDAR로 옮긴 법"): dict(
        status="다름 (말: '수치표면모델 메시'가 아니라 항공 LiDAR 삼각망)",
        value=" 발주문의 '수치표면모델 메시'는 이 삼각망을 가리킨다. 저장소에서 '수치표면모델'(DSM)은 다른 사전 정보 종류의 이름이라, 글에서는 "
              "'항공 LiDAR 삼각망'이 맞다."),
    ("A", "평가 영상과 탐색 지역 MVS"): dict(method="; " + RECHECK),
    ("B", "탐색 지역 MVS에 든 실험 지역 평가 영상"): dict(method="; " + RECHECK),
}
SPLIT = re.compile(r"(?<!\\)\|")
STATUS_CLASSES = ("확인 불가", "다름", "확인")
REF = re.compile(r"(?<![\w.])((?:2\.[1-68])-\d+|D-\d+)(?![\w])")


def norm(s):
    s = s.replace("`REPO/", "`").replace("`저장소/", "`")
    s = re.sub(r"(?:/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/)?phase-payloads/p0-audit", "P0", s)
    s = re.sub(r"(?:/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/)?phase-payloads/phd/(\w+)/PHD-[A-Z0-9-]+-v1",
               lambda m: PAYLOAD.get(m.group(1), m.group(0)), s)
    s = re.sub(r"\bPP/(\w+)/PHD-[A-Z0-9-]+-v1", lambda m: PAYLOAD.get(m.group(1), m.group(0)), s)
    return s


def cells(line):
    c = [x.strip() for x in SPLIT.split(line.strip())]
    return c[1:-1] if line.strip().startswith("|") and line.strip().endswith("|") else c


def fact_rows(path, heading):
    """the rows of the first '사실 | 값 | 근거 | 확인 방법 | 상태' table under the heading (up to the next heading of any level)."""
    lines = path.read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip() == heading)
    rows, hdr = [], None
    for l in lines[i + 1:]:
        if l.startswith("#"):
            break
        if not l.strip().startswith("|"):
            if hdr is not None and rows:
                break
            continue
        c = cells(l)
        if hdr is None:
            hdr = c; assert hdr == ["사실", "값", "근거", "확인 방법", "상태"], (path, heading, hdr); continue
        if set(l.replace("|", "").strip()) <= set("-: "):
            continue
        assert len(c) == 5, (path, heading, l[:120])
        rows.append(c)
    assert rows, (path, heading)
    return rows


def status_class(s):
    return next(k for k in STATUS_CLASSES if s.startswith(k))


def unesc(s):
    return s.replace("\\|", "|")


def main():
    rows, used = [], set()
    md, extra_md = [], {}
    for sid, title, notes, parts in SECTIONS:
        n = 0; sec_rows = []
        for w, heading, sub in parts:
            for fact, val, ev, meth, st in fact_rows(SRC[w], heading):
                fx = next((v for (fw, start), v in FIXES.items() if fw == w and fact.startswith(start)), None)
                if fx:
                    used.add(next(k for k in FIXES if k[0] == w and fact.startswith(k[1])))
                    val = val + fx.get("value", ""); meth = meth + fx.get("method", ""); st = fx.get("status", st)
                n += 1
                sec_rows.append(dict(no=f"{sid}-{n}", section=sid, section_title=title, subsection=sub, writer=w,
                                     fact=norm(fact), value=norm(val), evidence=norm(ev), method=norm(meth), status=st,
                                     status_class=status_class(st)))
        rows += sec_rows
        md.append(f"## {'3. ' if sid == 'D' else sid + ' '}{title}\n")
        md += notes + ([""] if notes else [])
        cur = object()
        for r in sec_rows:
            if r["subsection"] != cur:
                if r["subsection"]:
                    md.append(f"### {sid} {r['subsection']}\n")
                md.append("| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |"); md.append("|---|---|---|---|---|---|")
                cur = r["subsection"]
            md.append(f"| {r['no']} | {r['fact']} | {r['value']} | {r['evidence']} | {r['method']} | {r['status']} |")
            if r is not sec_rows[-1] and sec_rows[sec_rows.index(r) + 1]["subsection"] != cur:
                md.append("")
        md.append("")
        for esid, w, first, stop in EXTRA:
            if esid != sid:
                continue
            L = SRC[w].read_text().splitlines()
            i = next(k for k, l in enumerate(L) if l.startswith(first))
            j = next((k for k in range(i + 1, len(L)) if L[k].startswith(stop)), len(L))
            blk = [norm(l) for l in L[i:j]]
            while blk and not blk[-1].strip():
                blk.pop()
            md += blk + [""]; extra_md[sid] = "\n".join(blk)
    missing = set(FIXES) - used
    assert not missing, f"fixes not applied: {missing}"
    if "--list" in sys.argv:
        for r in rows:
            print(f"{r['no']:7s} {r['writer']} {r['status_class']:5s} {r['fact'][:70]}")
        return
    head = (HERE / "facts_head.md").read_text(); tail = (HERE / "facts_tail.md").read_text()
    nos = {r["no"]: r for r in rows}
    summary = {}
    for key, title in (("different", "### 지금 아는 것과 다른 것"), ("unconfirmed", "### 확인 불가")):
        blk = head.split(title, 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]
        group, items = "", []
        for l in blk.strip().splitlines():          # bold lines are group titles; numbered lines start items
            if l.startswith("**"):
                group = l.strip("* ")
            elif re.match(r"\d+\. ", l):
                items.append([group, l])
            elif l.strip() and items:
                items[-1][1] += " " + l.strip()
        summary[key] = []
        for group, it in items:
            refs = REF.findall(it)
            assert refs, f"summary item without a row reference: {it[:80]}"
            for ref in refs:
                assert ref in nos, f"summary refers to a missing row {ref}"
            summary[key].append(dict(group=group, text=re.sub(r"^\d+\.\s*", "", it), rows=refs))
    listed = {x for k in summary for it in summary[k] for x in it["rows"]}
    unlisted = [r["no"] for r in rows if r["status_class"] != "확인" and r["no"] not in listed]
    assert not unlisted, f"rows with status 다름 / 확인 불가 missing from the summary: {unlisted}"
    counts = {k: sum(r["status_class"] == k for r in rows) for k in STATUS_CLASSES}
    head = head.replace("{{COUNTS}}", f"사실 {len(rows)}줄: 확인 {counts['확인']}, 다름 {counts['다름']}, 확인 불가 {counts['확인 불가']}")
    for ph, (w, heading) in TAIL_BLOCKS.items():          # writer blocks copied into the tail (after the heading, to the next one)
        L = SRC[w].read_text().splitlines()
        i = next(k for k, l in enumerate(L) if l.startswith(heading))
        j = next((k for k in range(i + 1, len(L)) if L[k].startswith("## ")), len(L))
        tail = tail.replace(ph, "\n".join(norm(l) for l in L[i + 1:j]).strip())
    text = head.rstrip() + "\n\n" + "\n".join(md).rstrip() + "\n\n" + tail.strip() + "\n"
    O = OUT / "final"; O.mkdir(exist_ok=True)
    (O / "facts_6_4.md").write_text(text)
    J = dict(task_id="PHD-CH6-FACTS64-v1", document="facts_6_4.md", order="발주문_v1.md",
             columns=["no", "fact", "value", "evidence", "method", "status"], status_classes=list(STATUS_CLASSES),
             path_short_names={v: f"JointBuildGS-artifacts/phase-payloads/phd/{k}/" for k, v in PAYLOAD.items()}
             | {"P0": "JointBuildGS-artifacts/phase-payloads/p0-audit/"},
             writers=dict(A="agent A: tasks 1, 6, appendix D", B="agent B: tasks 2, 3.1-3.4", C="agent C: tasks 4, 5",
                          M="main session: tasks 3.5, 8 (and task 7, the Figure 6.1 note in the tail)"),
             counts=dict(rows=len(rows), **counts),
             notes_md=head.split("\n## 0.", 1)[0].strip(),
             summary={k: [dict(group=x["group"], text=unesc(x["text"]), rows=x["rows"]) for x in v] for k, v in summary.items()},
             rows=[{k: (unesc(v) if isinstance(v, str) else v) for k, v in r.items()} for r in rows],
             section_extra_md=extra_md, appendix_md=tail.strip(),
             scientific_verdict=None)
    (O / "facts_6_4.json").write_text(json.dumps(J, ensure_ascii=False, indent=1) + "\n")
    print(f"rows {len(rows)} {counts}; summary different {len(summary['different'])}, unconfirmed {len(summary['unconfirmed'])}")


if __name__ == "__main__":
    main()
