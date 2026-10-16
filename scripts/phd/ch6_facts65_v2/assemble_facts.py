"""PHD-CH6-FACTS65-v2: the facts table facts_6_5_6_6.md and facts_6_5_6_6.json, assembled from the five writers' drafts
(agents/A: 2.1, 2.3; agents/B: 2.2; agents/C: 2.4-2.6; agents/D: 2.7 without item 5, 2.8, 2.10, 2.11; agents/M, the main
session: 2.7 item 5, 2.9, 2.12 with the three computations of this order) in the order's section order 2.1-2.12. Text only:
  - the rows are copied as the writers wrote them, with one path vocabulary (prefixes 'REPO/' and '저장소/' dropped, payload
    folders by the short names of PAYLOAD below); 2.7 merges the rows of D and M by their item number ('5번 ...');
  - a row number column is added (<section>-<n>);
  - the main session's status changes after re-checking the sources (FIXES, each with its reason in the row);
  - the writers' '[ ] 채울 말' tables are collected into one table;
  - the head (title, notes, summary) and the tail are the main session's text (facts_head.md, facts_tail.md next to this file).
    The summary's row references are checked: every row with '다름' or '확인 불가' and every row computed by this order
    ('이 발주에서 냄' in the status) must be listed.
(jointbuildgs:dev, CPU, standard library only)
  python assemble_facts.py [--list]      --list: print the assembled rows and stop
Writes /out/final/facts_6_5_6_6.md and /out/final/facts_6_5_6_6.json. scientific_verdict: null."""
import json
import re
import sys
from pathlib import Path

OUT = Path("/out"); AG = OUT / "agents"; HERE = Path(__file__).resolve().parent
PAYLOAD = {"main_prep_measure_v1": "PREP", "main_prep_discard_rule_v1": "DR", "main_stage0_v1": "S0", "main_stage1_v1": "S1",
           "main_stage2_v1": "S2", "main_stage3_v1": "S3", "main_fix_v1": "SF", "main_baselines_v1": "SB", "main_fill_v1": "SL",
           "main_numbers_v1": "NB", "geogs_p1p2p3_v1": "GG", "metrics_trial_v1": "MT", "ch6_support_v1": "CH6", "ch6_facts64_v1": "F64",
           "ch6_facts65_v2": "F65"}
SRC = {w: AG / w / f"facts_{w}.md" for w in "ABCDM"}
# (section id, title, note lines, writers whose '## <id> ...' table goes in, in this order)
SECTIONS = [
    ("2.1", "평가 범위와 영역 파일의 규칙 (일 1)", [], ["A"]),
    ("2.2", "지표의 셈법 (일 2)", [], ["B"]),
    ("2.3", "가상 시점 메시 (일 3)", [], ["A"]),
    ("2.4", "'달라졌다'의 기준과 미리 정한 기록 (일 4)", [], ["C"]),
    ("2.5", "학습 목록과 돌린 때 (일 5)", [], ["C"]),
    ("2.6", "같은 구현의 변형과 스위치 (일 6)", [], ["C"]),
    ("2.7", "학습 전 판정의 검증 (일 7)", [], ["D", "M"]),
    ("2.8", "관측의 증거가 약할 때의 조건 (일 8)", [], ["D"]),
    ("2.9", "B0 LoD2에서 사전 정보가 틀린 곳 (일 9)", [], ["M"]),
    ("2.10", "6.2가 약속한 나눔과 보정의 하한 (일 10)", [], ["D"]),
    ("2.11", "7장 그림의 자리를 고른 규칙 (일 11)", [], ["D"]),
    ("2.12", "허용 오차를 구할 때 이상치로 지운 몫 (일 12)", [], ["M"]),
]
MERGE_BY_ITEM = {"2.7"}
FIXES = {}            # (writer, start of the fact cell) -> dict(status=..., value=..., method=...)
SPLIT = re.compile(r"(?<!\\)\|")
STATUS_CLASSES = ("확인 불가", "다름", "확인")
REF = re.compile(r"(?<![\w.])(2\.(?:1[0-2]|[1-9])-\d+)(?![\w])")
COMPUTED = "이 발주에서 냄"


def norm(s):
    s = s.replace("`REPO/", "`").replace("`저장소/", "`")
    s = re.sub(r"(?:/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/)?phase-payloads/p0-audit", "P0", s)
    s = re.sub(r"(?:/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/)?phase-payloads/phd/(\w+)/PHD-[A-Z0-9-]+-v\d",
               lambda m: PAYLOAD.get(m.group(1), m.group(0)), s)
    s = re.sub(r"\bPP/(\w+)/PHD-[A-Z0-9-]+-v\d", lambda m: PAYLOAD.get(m.group(1), m.group(0)), s)
    s = s.replace("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/", "")
    return s


def cells(line):
    c = [x.strip() for x in SPLIT.split(line.strip())]
    return c[1:-1] if line.strip().startswith("|") and line.strip().endswith("|") else c


def section_lines(path, sid):
    """the lines under the heading '## <sid> ...' up to the next '## ' heading."""
    L = path.read_text().splitlines()
    hits = [k for k, l in enumerate(L) if l.startswith(f"## {sid} ") or l.strip() == f"## {sid}"]
    assert len(hits) == 1, (path, sid, hits)
    i = hits[0]
    j = next((k for k in range(i + 1, len(L)) if L[k].startswith("## ")), len(L))
    return L[i + 1:j]


def table_rows(lines, header, where):
    rows, hdr, tables = [], None, 0
    for l in lines:
        if not l.strip().startswith("|"):
            if hdr is not None:
                hdr = None
            continue
        c = cells(l)
        if hdr is None:
            hdr = c
            if hdr == header:
                tables += 1
            continue
        if set(l.replace("|", "").strip()) <= set("-: ") or hdr != header:
            continue
        assert len(c) == len(header), (where, l[:160])
        rows.append(c)
    return rows, tables


def status_class(s):
    return next((k for k in STATUS_CLASSES if s.startswith(k)), None)


def item_no(fact):
    m = re.match(r"\s*(\d+)\s*번", fact)
    return int(m.group(1)) if m else 99


def unesc(s):
    return s.replace("\\|", "|")


def main():
    rows, used, md = [], set(), []
    H = ["사실", "값", "근거", "확인 방법", "상태"]
    for sid, title, notes, writers in SECTIONS:
        part = []
        for w in writers:
            got, nt = table_rows(section_lines(SRC[w], sid), H, f"{w} {sid}")
            assert got, f"no fact rows: {w} {sid}"
            part += [(w, r) for r in got]
        if sid in MERGE_BY_ITEM:
            part = sorted(part, key=lambda wr: item_no(wr[1][0]))          # stable: same item keeps the writer order
        sec = []
        for n, (w, (fact, val, ev, meth, st)) in enumerate(part, 1):
            fact = re.sub(r"^\s*2\.\d+-\d+\s*", "", fact)              # agent C wrote its own row ids in front of the fact
            fx = next((v for (fw, start), v in FIXES.items() if fw == w and fact.startswith(start)), None)
            if fx:
                used.add(next(k for k in FIXES if k[0] == w and fact.startswith(k[1])))
                val += fx.get("value", ""); meth += fx.get("method", ""); st = fx.get("status", st)
            sc = status_class(st)
            assert sc, f"status not one of {STATUS_CLASSES}: {sid} {fact[:40]} -> {st[:40]}"
            sec.append(dict(no=f"{sid}-{n}", section=sid, section_title=title, writer=w, fact=norm(fact), value=norm(val),
                            evidence=norm(ev), method=norm(meth), status=st, status_class=sc, computed_here=COMPUTED in st))
        rows += sec
        md.append(f"## {sid} {title}\n"); md += notes + ([""] if notes else [])
        md.append("| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |"); md.append("|---|---|---|---|---|---|")
        md += [f"| {r['no']} | {r['fact']} | {r['value']} | {r['evidence']} | {r['method']} | {r['status']} |" for r in sec]
        md.append("")
    missing = set(FIXES) - used
    assert not missing, f"fixes not applied: {missing}"
    fills = []
    for w in "ABCDM":
        L = SRC[w].read_text().splitlines()
        k = [i for i, l in enumerate(L) if l.startswith("## [ ] 채울 말")]
        if not k:
            continue
        j = next((i for i in range(k[0] + 1, len(L)) if L[i].startswith("## ")), len(L))
        got, _ = table_rows(L[k[0] + 1:j], ["절", "논문의 문장", "채울 말", "구절로 고칠 수 있는지"], f"{w} fills")
        fills += [dict(writer=w, item=norm(a), sentence=norm(b), fill=norm(c), phrase_ok=norm(d)) for a, b, c, d in got]
    order = {s[0]: i for i, s in enumerate(SECTIONS)}
    fills.sort(key=lambda f: order.get(re.match(r"[\d.]+", f["item"]).group(0) if re.match(r"[\d.]+", f["item"]) else "", 99))
    if "--list" in sys.argv:
        for r in rows:
            print(f"{r['no']:7s} {r['writer']} {r['status_class']:5s} {'*' if r['computed_here'] else ' '} {r['fact'][:80]}")
        print("fills", len(fills))
        return
    head = (HERE / "facts_head.md").read_text(); tail = (HERE / "facts_tail.md").read_text()
    nos = {r["no"]: r for r in rows}
    summary = {}
    for key, title in (("different", "### 논문의 문장과 다른 것"), ("unconfirmed", "### 확인 불가"), ("computed", "### 이 발주에서 낸 값")):
        blk = head.split(title, 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]
        group, items = "", []
        for l in blk.strip().splitlines():
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
    listed = {k: {x for it in summary[k] for x in it["rows"]} for k in summary}
    unl = [r["no"] for r in rows if r["status_class"] != "확인" and r["no"] not in listed["different"] | listed["unconfirmed"]]
    assert not unl, f"rows with 다름 / 확인 불가 missing from the summary: {unl}"
    unc = [r["no"] for r in rows if r["computed_here"] and r["no"] not in listed["computed"]]
    assert not unc, f"rows computed by this order missing from the summary: {unc}"
    counts = {k: sum(r["status_class"] == k for r in rows) for k in STATUS_CLASSES}
    head = head.replace("{{COUNTS}}", f"사실 {len(rows)}줄: 확인 {counts['확인']}, 다름 {counts['다름']}, 확인 불가 {counts['확인 불가']} "
                                      f"(이 발주에서 낸 값 {sum(r['computed_here'] for r in rows)}줄)")
    F = ["## [ ] 채울 말", "", "논문의 문장을 옮기고 [ ] 자리에 들어갈 말을 적었다. 구절만으로 고칠 수 없는 것은 그렇다고 적었다.", "",
         "| 절 | 논문의 문장 | 채울 말 | 구절로 고칠 수 있는지 |", "|---|---|---|---|"]
    F += [f"| {f['item']} | {f['sentence']} | {f['fill']} | {f['phrase_ok']} |" for f in fills]
    text = head.rstrip() + "\n\n" + "\n".join(md).rstrip() + "\n\n" + "\n".join(F) + "\n\n" + tail.strip() + "\n"
    O = OUT / "final"; O.mkdir(exist_ok=True)
    (O / "facts_6_5_6_6.md").write_text(text)
    J = dict(task_id="PHD-CH6-FACTS65-v2", document="facts_6_5_6_6.md", order="발주문_v2.md",
             columns=["no", "fact", "value", "evidence", "method", "status"], status_classes=list(STATUS_CLASSES),
             path_short_names={v: f"JointBuildGS-artifacts/phase-payloads/phd/{k}/" for k, v in PAYLOAD.items()}
             | {"P0": "JointBuildGS-artifacts/phase-payloads/p0-audit/"},
             writers=dict(A="agent A: 2.1, 2.3", B="agent B: 2.2", C="agent C: 2.4, 2.5, 2.6", D="agent D: 2.7 (not item 5), 2.8, 2.10, 2.11",
                          M="main session: 2.7 item 5, 2.9, 2.12 (the three computations of this order)"),
             counts=dict(rows=len(rows), computed_here=sum(r["computed_here"] for r in rows), **counts),
             notes_md=head.split("\n## 0.", 1)[0].strip(),
             summary={k: [dict(group=x["group"], text=unesc(x["text"]), rows=x["rows"]) for x in v] for k, v in summary.items()},
             rows=[{k: (unesc(v) if isinstance(v, str) else v) for k, v in r.items()} for r in rows],
             fills=[{k: unesc(v) for k, v in f.items()} for f in fills], appendix_md=tail.strip(), scientific_verdict=None)
    (O / "facts_6_5_6_6.json").write_text(json.dumps(J, ensure_ascii=False, indent=1) + "\n")
    print(f"rows {len(rows)} {counts}; fills {len(fills)}; summary " + ", ".join(f"{k} {len(v)}" for k, v in summary.items()))


if __name__ == "__main__":
    main()
