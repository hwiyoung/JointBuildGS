"""The existing TSDF pipeline with both camera lists restricted to training views."""
import ast
from pathlib import Path
import mesh_pipeline as m
source=Path(m.__file__);tree=ast.parse(source.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prepare')
text=ast.unparse(fn)
text=text.replace("views = r['views']", "views = [v for v in r['views'] if not v['virtual']]")
line="canonical = json.loads((O / 'views' / f\"{job['site']}.json\").read_text())['views']"
assert line in text
text=text.replace(line,line+"\n    canonical = [v for v in canonical if not v['virtual']]")
exec(compile(text,str(source), 'exec'),m.__dict__)
if __name__=='__main__':m.main()
