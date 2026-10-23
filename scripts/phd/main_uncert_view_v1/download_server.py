"""Serve the frozen viewer and bounded, resumable result downloads (stdlib only)."""
import argparse
import functools
import json
import os
import re
import time
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit


def byte_range(value, size):
    """Return an inclusive single range; ignore unsupported syntax/multiple ranges."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:
        start, end = max(0, size - int(last)), size - 1
    if start > end or start >= size:
        raise ValueError("Unsatisfiable byte range")
    return start, end


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JBGSDownload/1.0"

    def end_headers(self):
        # Explicit EOF as well as Content-Length: no idle connection at completion.
        self.send_header("Connection", "close")
        self.close_connection = True
        super().end_headers()

    def send_head(self):
        self.transfer = None
        if not urlsplit(self.path).path.startswith('/downloads/'):
            return super().send_head()
        path = Path(self.translate_path(self.path)).resolve()
        root = (Path(self.directory) / 'downloads').resolve()
        if not path.is_relative_to(root) or not path.is_file():
            self.send_error(404, "Download not found")
            return None
        try:
            stream = path.open('rb')
        except OSError:
            self.send_error(404, "Download not found")
            return None
        st = os.fstat(stream.fileno())
        size = st.st_size
        etag = f'"{st.st_mtime_ns:x}-{size:x}"'
        start, end, status = 0, size - 1, 200
        requested = self.headers.get('Range') if self.command == 'GET' else None
        condition = self.headers.get('If-Range')
        if requested and condition and condition != etag:
            try:
                valid_date = int(parsedate_to_datetime(condition).timestamp()) == int(st.st_mtime)
            except (ValueError, TypeError, OverflowError):
                valid_date = False
            if not valid_date:
                requested = None
        if requested:
            try:
                span = byte_range(requested, size)
            except (ValueError, OverflowError):
                stream.close()
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                return None
            if span:
                start, end = span
                status = 206
        count = end - start + 1
        self.send_response(status)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Content-Length', str(count))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', self.date_time_string(st.st_mtime))
        self.send_header('Cache-Control', 'private, no-transform')
        fallback = re.sub(r'[^a-zA-Z0-9._-]', '_', path.name)
        self.send_header('Content-Disposition', f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(path.name)}')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        stream.seek(start)
        self.transfer = dict(file=path.name, status=status, start=start, expected_bytes=count)
        return stream

    def copyfile(self, source, outputfile):
        if self.transfer is None:
            return super().copyfile(source, outputfile)
        sent, started, outcome = 0, time.monotonic(), 'complete'
        try:
            remaining = self.transfer['expected_bytes']
            while remaining:
                block = source.read(min(1024 * 1024, remaining))
                if not block:
                    outcome = 'source_truncated'
                    break
                outputfile.write(block)
                sent += len(block)
                remaining -= len(block)
            outputfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            outcome = 'client_disconnected'
        self.log_message('download %s', json.dumps(dict(
            **self.transfer, sent_bytes=sent, outcome=outcome,
            elapsed_seconds=round(time.monotonic() - started, 3))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.bind, args.port), functools.partial(Handler, directory=args.directory))
    server.serve_forever()
