"""Preserve completion-time file hashes and bind the fixed run to its loaded source."""
import argparse,json,time
from train_calibration import OUT,save,sha,now

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--wait',action='store_true');a=ap.parse_args()
    root=OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0/attempt_1';path=root/'receipt.json'
    while not path.exists():
        if not a.wait:raise SystemExit('inflight receipt not yet written')
        time.sleep(5)
    row=json.loads(path.read_text())
    if row.get('source_binding_corrected'):return
    original=root/'receipt_at_completion_unadjusted.json';assert not original.exists()
    save(original,row)
    binding=OUT/'checks/monitor_v2/inflight_fixed_source_binding.json';b=json.loads(binding.read_text())
    row.update(source_files_observed_at_completion=row['source_sha256'],config_file_observed_at_completion=row['config_sha256'],
        source_sha256={p.split('/')[-1]:h for p,h in b['source_loaded_at_start'].items()},config_sha256=b['config_sha256'],
        source_binding_corrected=True,source_binding_receipt=str(binding),source_binding_sha256=sha(binding),
        original_completion_receipt_sha256=sha(original),correction_at=now(),
        correction_reason='original host runner hashed files at completion; running fixed process had loaded the previously frozen 77d97761 source before monitor v2 edits')
    save(path,row);print('inflight fixed provenance bound to loaded 77d97761 source; completion-file observations preserved')

if __name__=='__main__':main()
