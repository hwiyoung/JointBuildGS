"""Record actual agent inspection after figures have been displayed and reviewed."""
import argparse
from common import *
def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);ap.add_argument('--note',required=True);a=ap.parse_args()
    files=sorted((D/'figures'/a.stage).glob('*.png'));assert files
    result=dict(status='PASS',at=now(),reviewer='coding agent actual displayed-image inspection',scope=a.stage,note=a.note,
      files=[dict(file=str(f.relative_to(D)),sha256=sha(f),json_sha256=sha(f.with_suffix('.json'))) for f in files],scientific_verdict=None)
    dump(O/'gates'/('pilot_visual.json' if a.stage=='pilot' else 'visual.json'),result)
    dump(D/'tables'/f'{a.stage}_visual_review.json',result);print('visual review recorded',a.stage,len(files))
if __name__=='__main__':main()
