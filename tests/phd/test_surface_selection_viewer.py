from collections import OrderedDict
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen,Request
from urllib.error import HTTPError
import numpy as np

from scripts.phd.surface_selection_v1.serve import make_handler
from scripts.phd.surface_selection_v1.data import Store
from src.phd.surface_selection_v1.evidence import evaluate_unit
from tests.phd.test_source_candidate_photometry import plane,synthetic_views


class ViewerHTTPTests(unittest.TestCase):
    def test_routes_read_only_and_no_directory_escape(self):
        class Fake:
            def manifest(self):return {'scientific_verdict':None}
            def region(self,r):
                if r!='P1':raise KeyError(r)
                return {'id':'P1'}
            def evidence(self,r,u,pair,anchor):return {'anchor':anchor,'pair_id':pair}
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'index.html').write_text('viewer')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Fake(),temp))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                self.assertEqual(urlopen(base+'/').read(),b'viewer')
                self.assertEqual(json.load(urlopen(base+'/api/region/P1'))['id'],'P1')
                self.assertIsNone(json.load(urlopen(base+'/api/evidence/P1/3'))['anchor'])
                for path in ('/../AGENTS.md','/%2e%2e/AGENTS.md','/api/region/UNKNOWN','/downloads/../../raw'):
                    with self.assertRaises(HTTPError) as e:urlopen(base+path)
                    self.assertEqual(e.exception.code,404)
                with self.assertRaises(HTTPError) as e:urlopen(Request(base+'/api/manifest',data=b'{}',method='POST'))
                self.assertEqual(e.exception.code,405)
            finally:server.shutdown();server.server_close();thread.join()


class ViewerReplayTests(unittest.TestCase):
    def fixture(self,singleton=False):
        sources={'mvs':plane(10),'als':plane(12)}
        views=synthetic_views()
        for v in views:v.update(image_url='/images/P1/'+str(v['id']),name=str(v['id']))
        xy=np.array([[x,y] for x in np.arange(-3,3.01,.5) for y in np.arange(-3,3.01,.5)])
        unit=dict(id=0,mvs_ids=[0],als_ids=[] if singleton else [0],footprint_xy=xy.tolist(),tile_ids=list(range(len(xy))),area_m2=len(xy)*.25)
        scored=dict(sources)
        if singleton:scored['als']=dict(valid=False,support_points=np.empty((0,3)))
        observation,decision=evaluate_unit(unit,scored,views,{'photometry':{'max_views':4,'max_pairs':6}})
        store=Store.__new__(Store);store.replay_cache=OrderedDict()
        store.native={'P1':{s+'_xyz':v['support_points'] for s,v in sources.items()}}
        store.members={'P1':{s+suffix:np.zeros(len(v['support_points']),np.int32) for s,v in sources.items() for suffix in ('_component','_unit')}}
        store.regions={'P1':{'components':{s:[dict(v,valid=True)] for s,v in sources.items()}}}
        store.unit=lambda region,uid:dict(unit=unit,observation=observation,decision=decision)
        store._view_context=lambda region,ids:(views,{'mvs':{},'als':{}})
        return store

    def test_common_patch_replay_has_valid_native_image_contract(self):
        result=self.fixture().evidence('P1',0)
        self.assertTrue(result['available']);self.assertTrue(result['reproduced'])
        self.assertEqual(result['comparison_mode'],'COMMON_MASK_COMPARISON')
        self.assertEqual(len(result['patch']['mask']),81)
        self.assertEqual(result['reference']['url'],result['reference']['image_url'])
        self.assertIn(result['anchor'],result['anchor_indices_valid'])

    def test_singleton_uses_own_mask_not_fake_shared_comparison(self):
        result=self.fixture(True).evidence('P1',0)
        self.assertEqual(result['comparison_mode'],'INDEPENDENT_SOURCE_SUPPORT')
        self.assertFalse(any(result['common_mask']))
        self.assertTrue(any(result['patch']['source_masks']['mvs']))
        self.assertFalse(any(result['patch']['source_masks']['als']))
        self.assertNotIn('als',result['patch']['costs'])


if __name__=='__main__':unittest.main()
