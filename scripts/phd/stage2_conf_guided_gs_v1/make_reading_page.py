"""Render the table-reading note as a dashboard page (jointbuildgs:dev, CPU). scientific_verdict: null.

  python make_reading_page.py [--src TABLE_READING_ko_v2.md] [--out reading.html] [--title ...]
Mounts: /w (repository, ro), /s2 (payload; rw for dashboard/).

Source: docs/experiments/phd/stage2_conf_guided_gs_v1/<--src> (the repository copy of the note). Figures are
referenced as reading/<file>.png (dashboard/reading/, written by make_reading.py and compose_reading_shots.py) and the 3-D view
as surfels.html#<state>; both resolve next to the page on the dashboard server (port 8887). 3-D links open in a new tab."""
import argparse
import re
from pathlib import Path

import markdown

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="TABLE_READING_ko_v2.md")
ap.add_argument("--out", default="reading.html")
ap.add_argument("--title", default="칸별 결과 분석")
a = ap.parse_args()
SRC = Path("/w/docs/experiments/phd/stage2_conf_guided_gs_v1") / a.src
OUT = Path("/s2/dashboard") / a.out
text = re.sub(r"^ {2,3}(?=- )", "    ", SRC.read_text(), flags=re.M)         # nested lists: 2-3 spaces (GitHub) -> 4 (Python-Markdown)
lines = []                                                                  # a list right after a paragraph line needs a blank line
for ln in text.split("\n"):
    if re.match(r"^(- |\d+\. )", ln) and lines and lines[-1].strip() and not re.match(r"^(\s*- |\s*\d+\. |\|)", lines[-1]):
        lines.append("")
    lines.append(ln)
text = "\n".join(lines)
body = markdown.markdown(text, extensions=["tables", "toc"])
body = re.sub(r'<a href="(surfels\.html[^"]*)"', r'<a class="l3" href="\1" target="_blank" title="3D로 보기"', body)
body = re.sub(r'<img alt="([^"]*)" src="([^"]*)"', r'<a href="\2" target="_blank"><img alt="\1" src="\2"', body)
body = re.sub(r'(<img alt="[^"]*" src="[^"]*" ?/?>)', r'\1</a>', body)


def bust(m):                                                                # cache-busting: figures are regenerated in place
    src = m.group(2); f = OUT.parent / src
    return f'{m.group(1)}"{src}?v={int(f.stat().st_mtime)}"' if f.exists() else m.group(0)


body = re.sub(r'((?:src|href)=)"((?:reading|intent)/[^"?]+\.png)"', bust, body)
OUT.write_text(f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{a.title}</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --mute:#6e6e73; --line:#dcdce0; --panel:#f5f5f7; --link:#0b63c4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141416; --fg:#ececf0; --mute:#9a9aa3; --line:#34343a; --panel:#1d1d21; --link:#6cb4ff; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.65 system-ui, -apple-system, "Noto Sans KR", sans-serif; }}
main {{ max-width:1280px; margin:0 auto; padding:18px 16px 60px; }}
h1 {{ font-size:22px; margin:6px 0 10px; }}
h2 {{ font-size:18px; margin:34px 0 10px; padding-top:10px; border-top:1px solid var(--line); }}
h3 {{ font-size:15.5px; margin:22px 0 8px; }}
a {{ color:var(--link); }}
a.l3 {{ text-decoration:underline dotted; text-underline-offset:3px; }}
code {{ background:var(--panel); padding:1px 5px; border-radius:4px; font-size:13px; }}
table {{ border-collapse:collapse; margin:10px 0 14px; display:block; overflow-x:auto; max-width:100%; }}
th, td {{ padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-variant-numeric:tabular-nums; font-size:14px; }}
td:nth-child(-n+3) {{ white-space:nowrap; }}
th {{ font-size:13px; color:var(--mute); font-weight:600; white-space:nowrap; }}
img {{ max-width:100%; border-radius:8px; border:1px solid var(--line); display:block; margin:10px 0 6px; }}
blockquote {{ margin:12px 0; padding:8px 14px; background:var(--panel); border-left:4px solid #d9b84a; border-radius:6px; }}
blockquote p {{ margin:4px 0; }}
ul, ol {{ padding-left:22px; }}
li {{ margin:3px 0; }}
.top {{ font-size:13px; color:var(--mute); }}
</style>
</head>
<body>
<main>
<div class="top"><a href="intent.html">의도 점검</a> · <a href="surfels.html">가우시안 3D 보기</a> · <a href="index.html">진행 대시보드</a></div>
{body}
</main>
</body>
</html>
""")
print("wrote", OUT)
