"""묶음: 보고서, 표, 그림, 설정, SHA256SUMS. 사용: g5_bundle.py <이름 덧말(가 또는 빈칸)> <보고서 파일 이름>"""
from common import *
import zipfile
def main(tag, report):
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M'); name = f'PHD-MAIN-JUDGEGT-v1{"_" + tag if tag else ""}_{stamp}_light.zip'
    files = [D/report] + sorted(p for p in (D/'tables').rglob('*') if p.is_file() and (tag != '가' or '가' in p.parts) and not p.name.startswith('t3_reverse')) + sorted(p for p in (D/'figures').rglob('*') if p.is_file())   # 덧붙임 2: 역방향 표는 묶음에서 뺌
    if tag == '가2':   # 덧붙임 4: 보고, 표, 점검 묶음, 뷰어 확인 PNG(뷰어 HTML 은 묶음 밖, 경로만 index.json 에)
        files = [D/report] + sorted(p for p in (D/'tables/가2').rglob('*') if p.is_file()) + sorted(p for p in (D/'audit/가2').rglob('*') if p.is_file()) \
                + sorted(p for p in (D/'viewer/가2').glob('*') if p.is_file() and p.suffix in ('.png', '.json'))
    files += [D/'progress.md', D/'issues.md', C/'judgegt_v1.json', C/'judgegt_v1.lock.json'] + sorted((R/'scripts/phd/main_judgegt_v1').glob('*'))
    files = [f for f in files if f.exists() and f.is_file()]
    arc = lambda f: 'PHD-MAIN-JUDGEGT-v1/' + (str(f.relative_to(D)) if str(f).startswith(str(D)) else 'configs/' + f.name if str(f).startswith(str(C)) else 'scripts/' + f.name)
    sums = '\n'.join(f'{sha(f)}  {arc(f)}' for f in files) + '\n'
    (O/'delivery').mkdir(exist_ok=True); z = O/'delivery'/name
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as Z:
        for f in files: Z.write(f, arc(f))
        Z.writestr('PHD-MAIN-JUDGEGT-v1/SHA256SUMS', sums)
    dump(z.with_suffix('.json'), dict(at=now(), zip=str(z), sha256=sha(z), files=len(files) + 1, scientific_verdict=None)); print('ZIP', z, sha(z))
if __name__ == '__main__': main(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != '-' else '', sys.argv[2])
