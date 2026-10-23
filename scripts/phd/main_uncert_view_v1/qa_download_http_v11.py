"""Interrupt a real full-bundle response, resume it, and verify the saved bytes."""
import datetime
import hashlib
import http.client
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

url = sys.argv[1] if len(sys.argv) > 1 else 'http://192.168.10.203:8912/'
endpoint = urlsplit(url)
docs = Path('/docs/tables_v1_1')
expected = json.loads((docs / 'results_download.json').read_text())
path = '/downloads/' + expected['archive']


def request(method='GET', headers=None):
    connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=30)
    connection.request(method, path, headers=headers or {})
    return connection, connection.getresponse()


conn, response = request('HEAD')
headers = dict(response.getheaders())
assert response.status == 200
assert int(headers['Content-Length']) == expected['bytes']
assert headers['Accept-Ranges'] == 'bytes'
assert headers['Content-Disposition'].startswith('attachment;')
assert headers['Connection'] == 'close'
response.read()
conn.close()

conn, response = request()
offset = 1024 * 1024 + 7
prefix = response.read(offset)
assert len(prefix) == offset
response.close()
conn.close()  # Actual interruption of the original full response.
h = hashlib.sha256(prefix)
conn, response = request(headers={'Range': f'bytes={offset}-', 'If-Range': headers['ETag']})
resumed_headers = dict(response.getheaders())
assert response.status == 206
assert resumed_headers['Content-Range'] == f'bytes {offset}-{expected["bytes"]-1}/{expected["bytes"]}'
received = offset
for block in iter(lambda: response.read(1024 * 1024), b''):
    h.update(block)
    received += len(block)
conn.close()
assert received == expected['bytes']
assert h.hexdigest() == expected['sha256']
receipt = dict(url=url, made=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               response_headers=headers, resumed_headers=resumed_headers,
               interrupted_at_bytes=offset, received_bytes=received, sha256=h.hexdigest(),
               hash_matches=True, pass_result=True, scientific_verdict=None)
(docs / 'download_http_resume.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
