"""Exercise HTTP framing, resumption and frozen byte identity over real sockets."""
import functools
import http.client
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

MODULE = Path(__file__).resolve().parents[2] / 'scripts/phd/main_uncert_view_v1/download_server.py'
spec = importlib.util.spec_from_file_location('download_server', MODULE)
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class DownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / 'downloads').mkdir()
        cls.data = bytes(range(256)) * 4096
        (root / 'downloads/result.zip').write_bytes(cls.data)
        (root / 'downloads/empty.zip').write_bytes(b'')
        (root / 'index.html').write_text('viewer')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(server_module.Handler, directory=str(root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def get(self, headers=None, method='GET', path='/downloads/result.zip'):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_complete_and_explicit_attachment(self):
        code, headers, body = self.get()
        self.assertEqual((code, body), (200, self.data))
        self.assertEqual(headers['Content-Length'], str(len(self.data)))
        self.assertEqual(headers['Connection'], 'close')
        self.assertEqual(headers['Accept-Ranges'], 'bytes')
        self.assertIn('attachment; filename="result.zip"', headers['Content-Disposition'])

    def test_resume_reconstructs_original(self):
        code, headers, first = self.get({'Range': 'bytes=0-12344'})
        self.assertEqual(code, 206)
        code, headers, last = self.get({'Range': 'bytes=12345-', 'If-Range': headers['ETag']})
        self.assertEqual(code, 206)
        self.assertEqual(first + last, self.data)
        self.assertEqual(int(headers['Content-Length']), len(last))

    def test_suffix_and_final_byte(self):
        for request, wanted in [('bytes=-9', self.data[-9:]),
                                (f'bytes={len(self.data)-1}-999999999', self.data[-1:])]:
            code, headers, body = self.get({'Range': request})
            self.assertEqual((code, body), (206, wanted))
            self.assertTrue(headers['Content-Range'].endswith(f'/{len(self.data)}'))

    def test_unsatisfiable(self):
        for request in [f'bytes={len(self.data)}-', 'bytes=100-99', 'bytes=-0']:
            code, headers, body = self.get({'Range': request})
            self.assertEqual((code, body), (416, b''))
            self.assertEqual(headers['Content-Range'], f'bytes */{len(self.data)}')

    def test_if_range_stale_or_matching_date(self):
        _, headers, _ = self.get(method='HEAD')
        code, _, body = self.get({'Range': 'bytes=0-3', 'If-Range': headers['Last-Modified']})
        self.assertEqual((code, body), (206, self.data[:4]))
        for stale in ['"old-representation"', 'Wed, 01 Jan 2020 00:00:00 GMT', 'W/"weak"']:
            code, _, body = self.get({'Range': 'bytes=0-3', 'If-Range': stale})
            self.assertEqual((code, body), (200, self.data))

    def test_head_and_empty(self):
        code, headers, body = self.get({'Range': 'bytes=0-3'}, method='HEAD')
        self.assertEqual((code, body, int(headers['Content-Length'])), (200, b'', len(self.data)))
        code, headers, body = self.get(path='/downloads/empty.zip')
        self.assertEqual((code, body, headers['Content-Length']), (200, b'', '0'))

    def test_unsupported_ranges_ignored(self):
        for request in ['bytes=0-2,5-9', 'bytes=-', 'items=0-2']:
            code, _, body = self.get({'Range': request})
            self.assertEqual((code, body), (200, self.data))

    def test_missing_traversal_and_viewer(self):
        self.assertEqual(self.get(path='/downloads/absent.zip')[0], 404)
        self.assertEqual(self.get(path='/downloads/../index.html')[0], 404)
        code, headers, body = self.get(path='/index.html')
        self.assertEqual((code, body), (200, b'viewer'))
        self.assertNotIn('Content-Disposition', headers)


if __name__ == '__main__':
    unittest.main()
