"""Required new stage-1-cell fate counts for the six existing nojudge runs."""
import json
import sys
from inputs import OUT,SITES,PRIORS
import fates

for site in SITES:
    for prior in PRIORS:
        result='nojudge_'+prior+'_s0';path=OUT/'fates'/site/(prior+'__'+result+'.json')
        if path.exists():
            assert json.loads(path.read_text())['status']=='PASS'
            print(site,prior,'reuse own completed fate count',flush=True);continue
        sys.argv=['fates.py',site,prior,result];fates.main()
