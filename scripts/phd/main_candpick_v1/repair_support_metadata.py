"""Correct inherited ALS hash labels on new LoD2 support, preserving originals.

No geometry, membership, sigma, or source payload changes. Before training only.
"""
import json
from pathlib import Path
from input_audit import sha
from prepare_places import save


for unit in ['B173_LoD2', 'R1_LoD2']:
    root = Path('/out/scenes') / unit
    p = root / 'support/support.json'; old = json.loads(p.read_text())
    fixed = {name: sha(root / 'support' / name) for name in ['prior.npz', 'patch_sigma.npz', 'mvs_points.npy']}
    if old['payload_sha256'] == fixed: continue
    backup = root / 'support/support_inherited_hash_labels.json'
    assert not backup.exists(); backup.write_bytes(p.read_bytes())
    old['payload_sha256'] = fixed
    old['hash_label_correction'] = 'Copied ALS metadata retained its old prior/sigma hash labels. Recomputed for the new LoD2 files before training; geometry unchanged.'
    p.write_text(json.dumps(old, indent=2, allow_nan=False) + '\n')
    receipt = dict(unit=unit, original_metadata_sha256=sha(backup), corrected_metadata_sha256=sha(p),
                   actual_payload_sha256=fixed, payload_changed=False, optimizer_steps=0, scientific_verdict=None)
    save(root / 'support_metadata_correction.json', receipt)
    for report in [root / 'scene.json', Path('/docs/scenes') / (unit + '.json')]:
        value = json.loads(report.read_text())
        value['support']['sha256'] = sha(p); value['support']['bytes'] = p.stat().st_size
        value['support_metadata_correction'] = receipt
        report.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    print(unit, 'support metadata corrected; payload unchanged')
