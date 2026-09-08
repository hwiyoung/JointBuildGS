"""Verify the viewer's route and read-only boundary using an actual HTTP server."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from scripts.phd.source_candidate_viewer_v1.serve import make_handler


class DummyStore:
    def manifest(self):return {'regions':['P1','P2','P3'],'scientific_verdict':None}
    def image_path(self,region,view):raise KeyError('Unregistered image')
    def evidence(self,region,cid,pair,anchor):return dict(region=region,cell_id=cid,pair_id=pair,anchor=anchor)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        (root/'figures').mkdir();(root/'figures/figure_manifest.json').write_text('{"figures":[]}')
        (root/'index.html').write_text('<title>viewer</title>');(root/'secret.txt').write_text('private')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(DummyStore(),root,root/'three.js',root))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.thread.join();self.server.server_close();self.tmp.cleanup()

    def test_actual_http_read_only_and_allowlist(self):
        self.assertEqual(urlopen(self.base+'/').status,200)
        self.assertEqual(json.load(urlopen(self.base+'/api/manifest'))['regions'],['P1','P2','P3'])
        for route in ('/secret.txt','/../secret.txt','/%2e%2e/secret.txt','/figures/../secret.txt','/vendor/other.js'):
            with self.assertRaises(HTTPError) as raised:urlopen(self.base+route)
            self.assertEqual(raised.exception.code,404)
        with self.assertRaises(HTTPError) as raised:urlopen(Request(self.base+'/api/manifest',method='POST'))
        self.assertEqual(raised.exception.code,405)

    def test_explicit_and_automatic_anchor_and_invalid_input(self):
        auto=json.load(urlopen(self.base+'/api/evidence/P1/16'))
        self.assertIsNone(auto['anchor'])
        exact=json.load(urlopen(self.base+'/api/evidence/P1/16?pair_id=862%3E870&anchor=2'))
        self.assertEqual(exact['pair_id'],'862>870');self.assertEqual(exact['anchor'],2)
        with self.assertRaises(HTTPError) as raised:urlopen(self.base+'/api/evidence/P1/invalid')
        self.assertEqual(raised.exception.code,400)


if __name__=='__main__':unittest.main()
