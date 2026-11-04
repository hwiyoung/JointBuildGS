"""Read the additive delivery scope without changing the frozen training config."""
import json
from pathlib import Path

POLICY=Path(__file__).resolve().parents[3]/'configs/phd/main_finaltrain_v1/addendum_training_only.json'

def training_only(site):
    value=json.loads(POLICY.read_text())
    assert value['scope']=='TRAINING_AND_MODEL_SAVE_ONLY'
    return site in value['sites']

def require_postprocessing(site):
    if training_only(site):
        raise RuntimeError(f'{site}: FINALTRAIN addendum forbids mesh/scoring/figures; assigned to RESCORE addendum 3')
