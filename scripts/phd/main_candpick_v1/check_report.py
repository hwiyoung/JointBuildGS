"""Verify local report links, exported image references and source hashes."""
import json
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo
from input_audit import sha
from result_io import save


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references, self.images = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            self.references.append(attrs['href'])
        if tag == 'img':
            assert attrs.get('alt'), 'Image lacks a description'
            self.references.append(attrs['src'])
            self.images.append(attrs['src'])
        assert tag != 'script', 'Offline report must not require JavaScript'


def main():
    root = Path('/docs')
    sources = json.loads((root / 'results/report_sources.json').read_text())
    for name, digest in sources['hashes'].items():
        assert sha(root / 'results' / name) == digest, name
    assert sha(root / 'result_report.md') == sources['report_sha256']
    assert sha(root / 'result_report.html') == sources['html_sha256']
    parser = Links(); parser.feed((root / 'result_report.html').read_text())
    for ref in parser.references:
        parts = urlsplit(ref)
        assert not parts.scheme and not parts.netloc, ref
        if parts.path:
            assert (root / unquote(parts.path)).is_file(), ref
    status = json.loads((root / 'results/status.json').read_text())
    if status['completed_count'] == 24:
        assert len(parser.images) == 16, 'Four quantitative curves and four panels for each of three representatives'
    result = dict(status='PASS_STRUCTURE_AND_SOURCES', at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        completed_arms=status['completed_count'], references=len(parser.references),
        embedded_images=len(parser.images), browser_render_test='NOT_RUN; source structure and PNG assets checked',
        scientific_verdict=None)
    save(root / 'report_checks.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
