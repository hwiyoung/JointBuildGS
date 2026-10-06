#!/usr/bin/env python3
"""PHD-MAIN-STAGE0-v1 progress record (host, stdlib): payload progress.md, rewritten from progress.json.

  python3 progress.py task <5.x> <status> [note]        status: 대기 | 진행 | 끝 | 멈춤
  python3 progress.py now "<지금 하는 일>"
  python3 progress.py train <run> <iteration> <s_per_1000> <expected_end> [note]
  python3 progress.py estimate "<text>"
  python3 progress.py note "<text>"
The training watcher (run_stage0.py) imports update_training(). scientific_verdict: null."""
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
P = (REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1").resolve()
STATE = P / "logs/progress.json"
TASKS = [("5.1", "공용 모듈 v6와 학습 코드 r12, 확인(학습 없음)"), ("5.2", "B0 연직 포함 조건 다시 고르기"),
         ("5.3", "일치 영역 지도"), ("5.4", "0단계 시험 학습 4회(두 묶음)"), ("보고", "보고서, 커밋과 푸시")]


def now():
    return dt.datetime.now().strftime("%m-%d %H:%M")


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return dict(tasks={k: dict(name=n, status="대기", note="", at="") for k, n in TASKS}, now="", training={}, estimate="", notes=[])


def save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1, ensure_ascii=False))
    L = ["# 진행 기록 — PHD-MAIN-STAGE0-v1", "", f"고친 시각: {now()} (KST)", "", f"**지금 하는 일:** {s['now']}", ""]
    if s.get("estimate"):
        L += ["**예상:** " + s["estimate"], ""]
    L += ["| 할 일 | 내용 | 상태 | 시각 | 메모 |", "|---|---|---|---|---|"]
    for k, n in TASKS:
        t = s["tasks"][k]
        L.append(f"| {k} | {t['name']} | {t['status']} | {t['at']} | {t['note']} |")
    if s["training"]:
        L += ["", "**학습**", "", "| 학습 | 반복 | 1,000회당 초 | 예상 끝 | 고친 시각 | 메모 |", "|---|---:|---:|---|---|---|"]
        for r, v in s["training"].items():
            L.append(f"| {r} | {v['iteration']:,} | {v['s_per_1000']} | {v['expected_end']} | {v['at']} | {v.get('note', '')} |")
    if s["notes"]:
        L += ["", "**기록**", ""] + [f"- {x}" for x in s["notes"]]
    (P / "progress.md").write_text("\n".join(L) + "\n")


def update_training(run, iteration, s_per_1000, expected_end, note=""):
    s = load()
    s["training"][run] = dict(iteration=int(iteration), s_per_1000=s_per_1000, expected_end=expected_end, at=now(), note=note)
    save(s)


def main():
    a = sys.argv[1:]
    s = load()
    if a[0] == "task":
        t = s["tasks"][a[1]]; t["status"] = a[2]; t["at"] = now(); t["note"] = a[3] if len(a) > 3 else t["note"]
    elif a[0] == "now":
        s["now"] = a[1]
    elif a[0] == "train":
        save(s); update_training(a[1], a[2], a[3], a[4], a[5] if len(a) > 5 else ""); return
    elif a[0] == "estimate":
        s["estimate"] = a[1]
    elif a[0] == "note":
        s["notes"].append(f"{now()} {a[1]}")
    save(s)


if __name__ == "__main__":
    main()
