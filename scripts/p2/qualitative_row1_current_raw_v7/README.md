# Superseded browser-overlay experiment

This directory is not the active row-1 renderer.

The `qualitative_row1_current_raw_v7` path assembled source JPEGs and reference
coordinates for a browser to redraw as SVG. It was useful for diagnosing datum and
selection problems, but it does not preserve the exact visual output that the human
reviewer accepted in `preview10_v4.py`. Its add-once artifacts remain external for
audit and are not deleted or overwritten.

The active renderer is:

- `scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py`
- full-199 membership driver:
  `scripts/p2/qualitative_row1_current_raw_v6/render199_v1.py`
- web rule: copy and display the rendered PNG bytes; do not redraw rooflines in the
  browser.

Scientific verdict remains `null`.
