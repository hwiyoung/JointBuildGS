"""Execute one frozen integration suite; every output is a new directory."""
import argparse
from pathlib import Path
from scripts.phd.p2_ab_v1 import c_evaluate,c_common_appearance,c_summarize


def main(args):
    cfg=c_evaluate.read(args.config);base=args.base
    for key in ['output','appearance_output','summary_output']:
        if (base/cfg[key]).exists():raise FileExistsError(base/cfg[key])
    b=[base/name for name in cfg['b_roots']]
    c_evaluate.main(argparse.Namespace(common=base/cfg['common'],reference=base/cfg['reference'],
        a_root=base/cfg['a_root'],b_root=b,output=base/cfg['output'],
        config=c_evaluate.REPO/cfg['evaluation_config']))
    c_common_appearance.main(argparse.Namespace(image_root=base/'PHD-P2-AB-B-IMAGE-v1',
        prior_root=base/'PHD-P2-AB-B-PRIOR-v2',b_root=b,output=base/cfg['appearance_output']))
    c_summarize.main(argparse.Namespace(integrated=base/cfg['output'],appearance=base/cfg['appearance_output'],
        output=base/cfg['summary_output']))
    c_evaluate.write(base/cfg['summary_output']/'suite_config_snapshot.json',cfg)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    main(p.parse_args())
