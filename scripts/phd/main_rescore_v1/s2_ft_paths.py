"""Resolve the successful attempt named by the FINALTRAIN receipt."""
from common import Path,PH
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
def model_path(receipt,site,prior):
    assert receipt['site']==site and receipt['prior']==prior
    model=Path(receipt['attempts'][-1]['model'])
    if model.is_relative_to('/out'):model=FT/model.relative_to('/out')
    assert model.is_relative_to(FT/'runs'/site/f'ft_{prior}_s0')
    return model
