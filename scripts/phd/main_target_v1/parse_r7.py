"""Compile syntax using the actual project Python without writing bytecode."""
import ast
from common import *
def main():
    files=list((REPO/'scripts/phd/main_target_v1').glob('*r7.py'))+list((REPO/'src/phd/forks/GeoGS-conf-guided-v1-r21').rglob('*.py'))
    for p in files:ast.parse(p.read_text(),filename=str(p))
    print('R7_PYTHON_SYNTAX_PASS',len(files),flush=True)
if __name__=='__main__':main()
