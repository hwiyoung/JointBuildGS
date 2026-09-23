"""Compose the 3-D-view screenshots of the table-reading note into captioned figures (jointbuildgs:dev, CPU).
scientific_verdict: null.

  python compose_reading_shots.py --shots <dir with the PNGs below>
Mounts: /s2 (payload; rw for dashboard/reading/), the shots directory, the Noto CJK fonts at /fonts.

The shots are taken on the host from the dashboard (port 8887) with headless Chrome, 1600 x 1100, e.g.
  google-chrome --headless=new --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader --hide-scrollbars \
    --window-size=1600,1100 --virtual-time-budget=90000 --screenshot=walk1.png "http://<host>:8887/surfels.html#<hash>"
with <hash> (all begin prior=M&scene=N):
  walk1     target=judge&mode=1&region=1&cls=2&slab=off&preset=0024&exag=1&ovPrior=false&ovUnseen=false
  walk2     target=judge&mode=7&region=1&cls=2&slab=off&preset=0024&exag=1&ovPrior=false&ovUnseen=false
  walk3     target=surface&mode=2&region=1&cls=2&slab=off&preset=0024&ovPrior=false&ovPhoto=false&ovUnseen=false
  walk4     target=surface&mode=3&region=1&cls=2&slab=off&preset=0024&ovPrior=false&ovPhoto=false&ovUnseen=false
  classes4  target=surface&mode=1&region=0&cls=0&slab=off&preset=0024&ovPrior=false&ovPhoto=false&ovUnseen=false
  windowcol target=surface&mode=1&region=2&cls=0&slab=across&slabPos=7.09&slabW=3&ovPrior=false&ovPhoto=false&ovUnseen=false
            &cam=123.933,57.234,-32.488,1.1951,0.02,5
  back      target=surface&mode=1&region=0&cls=0&slab=off&preset=back&ovPrior=false&ovPhoto=false&ovUnseen=true
Numbers in the captions are read from eval/intent_30000.csv and eval/unseen_30000.csv (the same tables the pages show).
Outputs: dashboard/reading/{walkthrough,classes4,wallcol,unseen_back}.png. The unmeasured (purple) pixels of the front wall
are the textureless plaster between the windows, not the windows (checked on the photos, 2026-09-29); the pages up to v6
used windowcol.png / back.png, which are kept as they were."""
import argparse
import csv
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

S2 = Path("/s2"); OUT = S2 / "dashboard/reading"
ap = argparse.ArgumentParser()
ap.add_argument("--shots", required=True)
ap.add_argument("--iteration", type=int, default=30000)
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
for f in ("/fonts/NotoSansCJK-Medium.ttc", "/fonts/NotoSansCJK-Regular.ttc"):
    if Path(f).exists():
        font_manager.fontManager.addfont(f); plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name(); break
T = {(r["condition"], r["region"], r["cls"]): r for r in csv.DictReader((S2 / "eval" / f"intent_{a.iteration}.csv").open())}
U = {(r["condition"], r["group"]): r for r in csv.DictReader((S2 / "eval" / f"unseen_{a.iteration}.csv").open())}
pc = lambda c, k="followed", r="roof", cl="conflict": f"{float(T[(c, r, cl)][k]) * 100:.0f}"   # noqa: E731
cm = lambda c, k="err_result", r="roof", cl="conflict": f"{float(T[(c, r, cl)][k]) * 100:.0f}"  # noqa: E731


def shot(name, y0=192, y1=1012):
    return cv2.cvtColor(cv2.imread(str(Path(a.shots) / f"{name}.png"))[y0:y1, :], cv2.COLOR_BGR2RGB)


# 1. one table row, step by step (LoD2 . normal . roof . conflict)
share = float(T[("P_M_N", "roof", "conflict")]["share"]) * 100
fig = plt.figure(figsize=(20, 14.2))
fig.text(0.01, 0.985, "표 한 줄 ↔ 3D: LoD2 · 정상 · 지붕 · 충돌 줄 (정리한 참값 기준)", fontsize=17, va="top", weight="bold")
fig.text(0.01, 0.955, f"칸 충돌 ({share:.1f} %)   |   소스 오차: 사진 {cm('P_M_N', 'err_photos')} cm / LoD2 {cm('P_M_N', 'err_prior')} cm   |   "
         f"P 판정 켬: {pc('P_M_N')} % · {cm('P_M_N')} cm   |   P0 판정 끔: {pc('P0_M_N')} % · {cm('P0_M_N')} cm   |   "
         f"O: {pc('O_M_N')} % · {cm('O_M_N')} cm   |   I: {pc('I')} % · {cm('I')} cm",
         fontsize=13.5, va="top", bbox=dict(boxstyle="round", fc="#fff6d6", ec="#d9b84a"))
caps = [("walk1", f"① 비율 {share:.1f} %  →  막대 보기 · 칸 = 충돌",
         "화면의 점 = 표의 '지붕 충돌' 픽셀(4 % 표본; 창 아래 '표 ‖ 화면 점'이 같은 값).\n"
         "막대 = 사진 → LoD2: 건물 끝 빨간 쐐기(LoD2가 위), 날개 청록(LoD2가 아래), 자홍 토막 = 3 m 넘는 차이(다른 물체를 잼)."),
        ("walk2", f"② 소스 오차 LoD2 {cm('P_M_N', 'err_prior')} cm  →  막대 보기 · 색 = 옛 자료 − 참값",
         f"진한 빨강 = LoD2가 참값보다 높은 곳 = 건물 끝 쐐기. 이 칸 점들의 |LoD2 − 참값| 중앙값 {cm('P_M_N', 'err_prior')} cm.\n"
         f"색을 '사진 − 참값'으로 바꾸면 거의 흰색 = 소스 오차 사진 {cm('P_M_N', 'err_photos')} cm."),
        ("walk3", f"③ P {pc('P_M_N')} % · P0 {pc('P0_M_N')} %  →  결과 보기 · 색 = 판정대로?",
         f"초록 = 그 조건의 결과가 사진 자리(τ 5.7 cm 안)로 간 픽셀. P는 {pc('P_M_N')} %가 초록,\n"
         f"P0는 {pc('P0_M_N')} % — 끝 쐐기가 통째로 빨강(LoD2 자리에 머묾)."),
        ("walk4", f"④ P {cm('P_M_N')} cm · P0 {cm('P0_M_N')} cm  →  결과 보기 · 색 = 결과 − 참값",
         f"흰색 = 참값 근처. P는 거의 흰색(|결과 − 참값| 중앙값 {cm('P_M_N')} cm),\n"
         f"P0는 끝 쐐기가 빨강(LoD2처럼 높음) → {cm('P0_M_N')} cm.")]
for i, (n, t, c) in enumerate(caps):
    ax = fig.add_axes([0.01 + (i % 2) * 0.5, 0.49 - (i // 2) * 0.465, 0.48, 0.36]); ax.imshow(shot(n)); ax.set_axis_off()
    fig.text(0.01 + (i % 2) * 0.5, 0.905 - (i // 2) * 0.465, t, fontsize=14, weight="bold", va="top")
    fig.text(0.01 + (i % 2) * 0.5, 0.878 - (i // 2) * 0.465, c, fontsize=11, va="top", color="#333")
fig.savefig(OUT / "walkthrough.png", dpi=100); plt.close(fig)


def panes(name, title, notes, sub):
    """Four synchronised panes (P, P0 / O, I) of one screenshot with a note in each pane."""
    img = shot(name)
    fig = plt.figure(figsize=(16, 9.6))
    ax = fig.add_axes([0, 0, 1, 0.9]); ax.imshow(img); ax.set_axis_off()
    fig.text(0.01, 0.985, title, fontsize=15, weight="bold", va="top")
    fig.text(0.01, 0.945, sub, fontsize=11, va="top", color="#333")
    h, w = img.shape[:2]
    for (px, py), t in zip(((0.01, 0.075), (0.51, 0.075), (0.01, 0.575), (0.51, 0.575)), notes):
        ax.text(px * w, py * h + 22, t, fontsize=10.5, color="#111", va="top", bbox=dict(boxstyle="round", fc="#fffbe6", ec="#d9b84a", alpha=0.95))
    return fig


# 2. the same classes look different per condition (whole building)
b = (S2 / "dashboard/surfels/inputs_M_N.bin").read_bytes()                  # the viewer's 4 % sample (same pixels in every pane)
rec = np.frombuffer(b[16:], np.float32).reshape(-1, int(np.frombuffer(b[12:16], np.uint32)[0]))
cnt = {(r, k): int(((rec[:, 8] == r) & (rec[:, 7] == k)).sum()) for r in (1, 2) for k in (1, 2, 3)}
fig = panes("classes4", "같은 칸, 다른 자리 — 네 창의 점은 같은 픽셀이고 칸도 같다",
            ["P: 무늬 없는 벽면(보라)이 LoD2 자리에 남아 잰 벽(주황)보다\n약 17 cm 앞 → 밖에서 보면 보라가 덮는다",
             "P0: 모든 픽셀이 LoD2 면 한 장에 → 칸 색이\n같은 깊이에서 섞여 벽면 줄무늬가 그대로 보인다",
             "O: 전체가 약 0.3~0.4 m 떠 있고, 지붕 못 잼 픽셀이\n일치보다 약 8 cm 더 높아 곳곳에서 보라가 위에 보인다",
             "I: 무늬 없는 벽면이 잰 벽보다 약 4 cm 안쪽\n→ 밖에서 보면 주황 벽이 벽면을 덮는다"],
            f"네 창의 점 수는 같다 — 지붕 일치 {cnt[(1, 1)]:,} · 충돌 {cnt[(1, 2)]:,} · 못 잼 {cnt[(1, 3)]:,}, 벽 {cnt[(2, 1)]:,} · {cnt[(2, 2)]:,} · {cnt[(2, 3)]:,}"
            "(4 % 표본). 다른 것은 각 조건이 그 픽셀을 놓은 깊이뿐이고, 여러 사진이 같은 자리를 보면 앞에 있는 점의 색이 보인다.")
fig.savefig(OUT / "classes4.png", dpi=100); plt.close(fig)

# 3. a 3 m slab through a column of the front wall, seen from the side (terms: stage-2 results terminology, 2026-09-29)
fig = panes("windowcol", "옆에서 본 정면 벽 한 줄(단면 두께 3 m) — 왼쪽 = 바깥(길 쪽), 오른쪽 = 건물 안",
            ["P: 보라(무늬 없는 벽면, 미측정) = LoD2(prior) 자리 근처,\n주황(창·창틀·장식, 충돌) = 약 20 cm 안쪽(영상 깊이)",
             "P0: 보라·주황 모두 LoD2 자리\n(한 줄) — 판정이 없어 전부 prior",
             "O: 두 판정 모두 LoD2와 영상 깊이 사이에\n퍼짐(치우친 카메라 가정)",
             "I: 주황 = 영상 깊이, 보라(무늬 없는 벽면)는\n그보다 약 4 cm 안쪽"],
            "점 색 = 판정(보라 미측정, 주황 충돌, 파랑 일치). 가로 거리가 곧 '결과가 어디에 놓였나'다.")
fig.savefig(OUT / "wallcol.png", dpi=100); plt.close(fig)

# 4. the faces no photo sees (behind the building)
cov = lambda c, g: f"{float(U[(c, g)]['coverage']) * 100:.0f}"  # noqa: E731
fig = panes("back", "비가시 면 — 건물 뒤에서 본 모습(청록 = 비가시 면에 남은 원반, 이번 실행 r5)",
            [f"P: 뒷지붕 {cov('P_M_N', 'roof')} %·뒷벽 {cov('P_M_N', 'wall')} %가 prior\n원반으로 남음(시작 100 %·96 %)",
             f"P0: 뒷지붕 {cov('P0_M_N', 'roof')} %·뒷벽 {cov('P0_M_N', 'wall')} % — 같은 prior로\n시작했지만 고정이 없어 사라짐",
             f"O: 뒷지붕 {cov('O_M_N', 'roof')} %·뒷벽 {cov('O_M_N', 'wall')} %",
             f"I: 뒷지붕 {cov('I', 'roof')} %·뒷벽 {cov('I', 'wall')} %\n(prior 없음)"],
            "비가시 면은 판정 표에 없다(판정은 영상 픽셀만 센다). 덮임 = LoD2 면 ±0.3 m 안에 불투명 원반이 있는 1 m 칸의 몫(eval/unseen_30000.csv). "
            "회색 격자 = 그 면의 LoD2 자리.\n방법론 4.2('어느 영상에도 보이지 않는 점은 뺀다')대로 고친 r6에서는 이 면의 prior가 처음부터 빠진다.")
fig.savefig(OUT / "unseen_back.png", dpi=100); plt.close(fig)
print("done")
