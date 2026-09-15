"""Publish immutable app/publisher snapshots with the previous containers retained."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('attempt',type=Path);ap.add_argument('--version',required=True);ap.add_argument('--previous',required=True);a=ap.parse_args()
root=a.attempt.resolve();repo=Path(__file__).resolve().parents[3];version=a.version
app=root/'viewer'/('app_'+version);publisher=root/'viewer'/('publisher_'+version)
shutil.copytree(repo/'src/apps/r1r5_comparison_v1',app)
shutil.copytree(root/'viewer'/('publisher_'+a.previous),publisher)
shutil.copy2(repo/'scripts/phd/r1r5_comparison_v1/publish.py',publisher/'publish.py')
for path in [app,publisher]:
    (path/'snapshot_hashes.json').write_text(json.dumps({str(f.relative_to(path)):hashlib.sha256(f.read_bytes()).hexdigest() for f in path.rglob('*') if f.is_file()},indent=2))
commands={}
for role in ['publisher','viewer']:
    cmd=json.loads((root/'viewer'/(role+'_command.json')).read_text())
    cmd[cmd.index('--name')+1]=f'jbgs-r1r5-{role}-8913-{version}'
    for i,item in enumerate(cmd):
        if item.startswith('type=bind,') and ',target=/app,' in item:cmd[i]=f'type=bind,source={app},target=/app,readonly'
        if item.startswith('type=bind,') and ',target=/driver,' in item:cmd[i]=f'type=bind,source={publisher},target=/driver,readonly'
    commands[role]=cmd
    (root/'viewer'/f'{role}_command_{version}.json').write_text(json.dumps(cmd,indent=2))
for role,cmd in commands.items():
    old=f'jbgs-r1r5-{role}-8913-{a.previous}'
    subprocess.run(['docker','stop',old],check=True,stdout=subprocess.DEVNULL)
    try:subprocess.run(cmd,check=True)
    except Exception:
        subprocess.run(['docker','start',old],check=True);raise
print('http://127.0.0.1:8913/')
