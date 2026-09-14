import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from scripts.phd.source_selected_2dgs_v1.control import check_outputs, check_receipt, gate, sha


class ReceiptControlTests(unittest.TestCase):
    def test_recorded_payload_change_fails(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'data').write_bytes(b'original')
            receipt={'outputs':{'data':sha(p/'data')}}
            check_outputs(p,receipt)
            (p/'data').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):check_outputs(p,receipt)

    def test_receipt_cannot_verify_files_outside_owner(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'escapes'):
                check_outputs(Path(root),{'outputs':[{'path':'../outside','sha256':'0'*64}]})

    def test_incomplete_or_scientific_verdict_cannot_pass(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            for state,verdict in [('RUNNING',None),('PASS','accepted')]:
                (p/'receipt.json').write_text(json.dumps(dict(status=state,scientific_verdict=verdict)))
                with self.assertRaisesRegex(ValueError,'PASS/null'):check_receipt(p)
            (p/'receipt.json').write_text(json.dumps(dict(status='PASS')))
            with self.assertRaisesRegex(ValueError,'PASS/null'):check_receipt(p)

    def test_training_gate_handles_actual_repeat_map_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            config=p/'source_snapshot/configs/phd/source_selected_2dgs_v1/experiment.json'
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({'training':{'iterations':50,'checkpoints':[0,50],
                'maximum_center_displacement_m':.25}}))
            manifest=p/'prepared/P2/manifest.json';manifest.parent.mkdir(parents=True);manifest.write_text('{}')
            folder=p/'training/P2/source_selected';folder.mkdir(parents=True)
            for step in (0,50):(folder/f'checkpoint_{step:06d}.npz').write_bytes(b'sealed fixture')
            receipt=dict(status='PASS_SOURCE_SELECTED_2DGS_TRAIN',scientific_verdict=None,
                config_sha256=sha(config),manifest_sha256=sha(manifest),region='P2',arm='source_selected',
                iterations=50,checkpoints=[0,50],input_hashes_unchanged=True,
                iteration0_repeat_max_abs=dict(rgb=0.,depth=0.,alpha=0.,normal=0.,view_id='fixture'),
                final_invariants=dict(means=True,quats_raw=True,log_scales=True,opacity_raw=True,
                    finite_parameters=True,maximum_center_displacement_m=.1),
                outputs={str(f.relative_to(folder)):sha(f) for f in folder.iterdir()})
            seal=folder/'receipt.json';seal.write_text(json.dumps(receipt))
            args=SimpleNamespace(attempt=p,preflight=False,region='P2',arm='source_selected')
            gate(args)
            receipt['iteration0_repeat_max_abs']['depth']=1e-4;seal.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'repeatable'):gate(args)


if __name__=='__main__':unittest.main()
