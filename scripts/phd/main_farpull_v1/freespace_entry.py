"""Opt-in AST additions; unchanged base files and existing processes are preserved."""
import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path


def instrument(text):
    tree=ast.parse(text);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='training')
    loop=next(n for n in fn.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='iteration')
    index=fn.body.index(loop)
    fn.body[index:index]=ast.parse('fs_control = freespace_training.create(args, gaussians)').body
    # Add once immediately before observations/backward, after the complete base loss.
    index=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='gaussians.optimizer.zero_grad')
    loop.body[index:index]=ast.parse('total_loss = jbgs_freespace.add_loss(total_loss, fs_control, judgment, viewpoint_cam, gaussians, render_pkg.get("fs_median_depth"), iteration)').body
    index=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.If) and 'jbgs_state.after_step' in ast.unparse(n.test))
    loop.body[index:index]=ast.parse('freespace_training.after_step(fs_control, locals())').body
    handler=ast.parse("try:\n pass\nexcept RuntimeError as exc:\n if str(exc).startswith('LOSSTRAIN_STOP:') and 'fs_control' in locals() and fs_control is not None:\n  freespace_training.save_stop(locals(), exc)\n raise").body[0]
    handler.body=fn.body;fn.body=[handler]
    tree.body.insert(0,ast.Import(names=[ast.alias(name='jbgs_freespace'),ast.alias(name='freespace_training')]))
    return ast.unparse(ast.fix_missing_locations(tree))+'\n'


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--jbgs_freespace',choices=['off','on'],default='off')
    parser.add_argument('--jbgs_freespace_lambda',type=float,default=0.)
    parser.add_argument('--jbgs_freespace_support')
    own,rest=parser.parse_known_args();sys.path.insert(0,'/source')
    import freespace_training as FT
    FT.OPTIONS=own
    # Capture median from the native RGB rasterization without adding a render.
    if own.jbgs_freespace=='on':FT.install_median()
    observer=Path('/repo/scripts/phd/main_floatdiag_v1/replay_observer.py').read_text()
    exec(compile(observer[:observer.index('sys.argv[0]=')],'<original-birth-observer>','exec'),{})
    model=Path(rest[rest.index('-m')+1]);model.mkdir(parents=True,exist_ok=True)
    base=Path('/source/train.py').read_text();code=instrument(base)
    target=model/'freespace_executed_train.py';target.write_text(code)
    (model/'freespace_instrumentation.json').write_text(json.dumps(dict(
        base_sha256=hashlib.sha256(base.encode()).hexdigest(),executed_sha256=hashlib.sha256(code.encode()).hexdigest(),
        options=vars(own),original_source_modified=False,scientific_verdict=None),indent=2)+'\n')
    sys.argv=['/source/train.py',*rest]
    exec(compile(code,str(target),'exec'),dict(__name__='__main__',__file__='/source/train.py'))


if __name__=='__main__':main()
