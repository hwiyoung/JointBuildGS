"""Read protection and optimizer-era metadata for an attributed final Gaussian."""
import json
from pathlib import Path
import torch

cfg=json.loads(Path('/config.json').read_text());folder=Path(cfg['complete']);i=cfg['gaussian_id']
state=torch.load(str(folder/'checkpoint.pth'),map_location='cpu',mmap=True)
model=state['model'];receipt=json.loads((folder/'receipt.json').read_text())
result=dict(status='PASS_SAVED_GAUSSIAN_STATE_READ',scientific_verdict=None,gaussian_id=i,
            checkpoint_sha256=receipt['checkpoint_sha256'],ply_sha256=receipt['ply_sha256'],
            iteration=state['iteration'],xyz=model[1][i].tolist(),scale=model[4][i].exp().tolist(),
            opacity=float(model[6][i].sigmoid()),
            protected=bool(state['frozen_mask'][i]) if state['frozen_mask'] is not None else None,
            completed=bool(state['completed_mask'][i]) if state['completed_mask'] is not None else None,
            freeze_done=state['runtime'].get('freeze_done'),
            densify_until_iter=state['optimization']['densify_until_iter'],
            limitation='Final state only; matched pair checkpoints locate when this behavior develops.')
Path('/out/receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
