"""Execute only named definitions from the byte-identical task-local copies."""
import ast
from common import HERE
def functions(filename,names,scope):
    p=HERE/'inherited'/filename
    tree=ast.parse(p.read_text());selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in selected}==set(names),(filename,names)
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(p),'exec'),scope)
    return [scope[n] for n in names]
