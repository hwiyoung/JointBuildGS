"""Append newly scored methods while retaining all existing metric rows."""
import sys
from add2_scores import metric_rows
from add2_common import D, json, table


def main(site, prior, arm):
    name = f'addendum2/stage1/{site}__{prior}'
    path = D/'tables'/(name+'.json')
    old = json.loads(path.read_text())['rows'] if path.exists() else []
    if any(r['method'] == arm for r in old):
        return
    table(name, old+metric_rows(site, prior, methods=[arm]))


if __name__ == '__main__':
    main(*sys.argv[1:])
