"""Create a new auditable copy of the exact official source with state hooks."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

TRAIN_SHA = '4c09f6a117d7f4a13e3bd3c5d9eb49b1830e428950a53c0f86be4001637c7a10'
RUNTIME_KEYS = (
    'ema_loss_for_log', 'ema_dist_for_log', 'ema_normal_for_log', 'ema_lod_loss', 'ema_da_loss',
    'freeze_done', 'dynamic_switch_triggered', 'dynamic_switch_iter', 'dynamic_switch_forced',
    'lod_loss_history', 'last_dynamic_check', 'da_phase', 'da_weight', 'da_depth_history',
    'da_monitor_depth', 'da_monitor_rgb', 'da_last_check', 'da_consecutive', 'da_locked_weight',
)

def replace_once(text, needle, replacement):
    if text.count(needle) != 1:
        raise ValueError(f'Pinned source boundary missing or ambiguous: {needle!r}')
    return text.replace(needle, replacement)

def instrument(source):
    text = replace_once(source, 'def training(dataset,', 'import jbgs_state\n\n\ndef training(dataset,')
    needle = '    progress_bar = tqdm(range(first_iter, opt.iterations), desc="Training progress")'
    restore = '    if args.jbgs_resume_full:\n        jbgs_restored = jbgs_state.restore_state(args.jbgs_resume_full, locals(), globals())\n'
    for name in ('first_iter', 'building_freeze_mask', 'viewpoint_stack', *RUNTIME_KEYS):
        restore += f'        {name} = jbgs_restored["{name}"]\n'
    text = replace_once(text, needle, restore + '\n' + needle)
    needle = '        with torch.no_grad():\n            if network_gui.conn is None:'
    text = replace_once(text, needle, '        if jbgs_state.after_step(locals()):\n            break\n\n' + needle)
    needle = '    args = parser.parse_args(sys.argv[1:])'
    text = replace_once(text, needle, '    jbgs_state.register_args(parser)\n' + needle + '\n    jbgs_state.validate_args(args)')
    compile(text, 'train.py', 'exec')
    return text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Run project tools in Docker')
    original = (args.source / 'train.py').read_bytes()
    if hashlib.sha256(original).hexdigest() != TRAIN_SHA:
        raise ValueError('Official train.py bytes differ from the audited commit')
    changed = instrument(original.decode())
    shutil.copytree(args.source, args.output, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    (args.output / 'train.py').write_text(changed)
    shutil.copyfile(Path(__file__).with_name('jbgs_state.py'), args.output / 'jbgs_state.py')
    patch = ''.join(difflib.unified_diff(original.decode().splitlines(True), changed.splitlines(True),
                                       fromfile='official/train.py', tofile='instrumented/train.py'))
    (args.output / 'jbgs_instrumentation.patch').write_text(patch)
    receipt = {'official_commit': 'db40c95c657ec03ff21c83cb99cf39f4e90247a6',
               'official_train_sha256': TRAIN_SHA,
               'instrumented_train_sha256': hashlib.sha256(changed.encode()).hexdigest(),
               'sidecar_sha256': hashlib.sha256((args.output / 'jbgs_state.py').read_bytes()).hexdigest(),
               'scientific_verdict': None, 'renderer_and_model_modified': False,
               'purpose': 'complete-state observability/resume and explicit refinement protection release'}
    (args.output / 'jbgs_instrumentation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
