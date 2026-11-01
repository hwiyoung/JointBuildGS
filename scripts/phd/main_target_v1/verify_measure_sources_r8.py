"""Verify r8 readout changes are path bindings and unchanged inherited arithmetic."""
import ast
from common import *
def node(path,name):return ast.dump(next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name==name))
def main():
    root=Path(__file__).parent;rows=[]
    for fn in ['prepare','score']:
        a=root/'post_continue_r7_lod2.py';b=root/'post_r8.py';assert node(a,fn)==node(b,fn);rows.append(dict(old=a.name,new=b.name,function=fn,AST_identical=True))
    for old,new in [('axes_continue_r7_lod2.py','axes_r8.py'),('fuse_final_continue_r7_lod2.py','fuse_final_r8.py'),('render_final_continue_r7_lod2.py','render_final_r8.py')]:
        a=(root/old).read_text();b=(root/new).read_text().replace('scoring_r8','scoring_continue_r7.r1').replace('r8/scoring','r7_continue/scoring').replace('r8/meshes','r7_continue/meshes').replace('tables/r8','tables/continue_r7')
        assert ast.dump(ast.parse(a))==ast.dump(ast.parse(b)),(old,new)
        rows.append(dict(old=old,new=new,path_binding_only=True,normalized_AST_identical=True))
    a=json.loads((CFG/'scoring_continue_r7.r1.json').read_text());b=json.loads((CFG/'scoring_r8.json').read_text())
    for k in ['source_files','axes','current_mesh','final_mesh']:assert a[k]==b[k],k
    for path,h in b['source_files'].items():assert sha(path)==h
    result=dict(at=stamp(),status='PASS_R8_INHERITED_SCORING_ARITHMETIC',rows=rows,source_files=b['source_files'],r7_arithmetic_parity=sha(OUT/'r7_continue/scoring/parity.json'),GT_training_input=False,scientific_verdict=None);dump(OUT/'r8/verification/measurement_sources.json',result);dump(DOC/'tables/r8_measurement_source_verification.json',result);print(result['status'])
if __name__=='__main__':main()
