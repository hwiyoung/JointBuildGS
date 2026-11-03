import ast
from pathlib import Path
for p in Path('/repo/scripts/phd/main_rescore_v1').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
print('PYTHON_SYNTAX_PASS')
