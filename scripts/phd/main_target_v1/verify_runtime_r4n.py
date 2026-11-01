"""Independently remove only TARGET hooks and compare the default-off AST to r18."""
import ast,difflib
from common import *

class WithoutTarget(ast.NodeTransformer):
    def visit_Import(self,node):
        return None if any(a.name=='jbgs_target' for a in node.names) else node
    def visit_Assign(self,node):
        if any(isinstance(t,ast.Name) and t.id=='target_control' for t in node.targets):return None
        return self.generic_visit(node)
    def visit_If(self,node):
        if ast.dump(node.test)==ast.dump(ast.parse('target_control is not None',mode='eval').body):
            return [self.visit(n) for n in node.orelse]
        return self.generic_visit(node)
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute):
            f=node.value.func
            if isinstance(f.value,ast.Name) and f.value.id=='jbgs_target':return None
        return self.generic_visit(node)

def main():
    cfg=json.loads((CFG/'target_v1.stage1.r4n.json').read_text());runtime=json.loads((CFG/'target_v1.runtime.r4n.lock.json').read_text())
    for name,digest in runtime['files'].items():assert sha(REPO/name)==digest,name
    fork=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19';base=json.loads((CFG/'fork_r19_base.json').read_text())
    old=(REPO/base['base']/'train.py').read_text();new=(fork/'train.py').read_text()
    assert sha(REPO/base['base']/'train.py')==base['base_file_sha256']['train.py']
    assert ast.dump(WithoutTarget().visit(ast.parse(new)))==ast.dump(ast.parse(old)),'default-off AST differs'
    changes=[];a=old.splitlines();b=new.splitlines()
    for tag,i,j,k,l in difflib.SequenceMatcher(a=a,b=b).get_opcodes():
        if tag!='equal':changes.append(dict(file='train.py',operation=tag,old_start=i+1,old_end=j,new_start=k+1,new_end=l))
    changes.append(dict(file='jbgs_target.py',operation='add',new_start=1,new_end=len((fork/'jbgs_target.py').read_text().splitlines())))
    (DOC/'tables/r19_train_r4n.patch').write_text('\n'.join(difflib.unified_diff(a,b,fromfile='r18/train.py',tofile='r19/train.py',lineterm=''))+'\n')
    dump(DOC/'tables/r19_changes_r4n.json',dict(changes=changes,scientific_verdict=None))
    result=dict(at=stamp(),status='PASS_DEFAULT_OFF_AST',base_sha256=base['base_file_sha256']['train.py'],
        runtime_lock_sha256=sha(CFG/'target_v1.runtime.r4n.lock.json'),runtime_files_verified=len(runtime['files']),
        validation='Removing TARGET-only import, initialization, argument registration and guarded branches exactly restores the r18 AST.',
        training_steps=0,scientific_verdict=None)
    dump(OUT/'r4n/verification/runtime.json',result);dump(DOC/'tables/runtime_verification_r4n.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
