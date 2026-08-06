# Web review implementation status

## Active path

The active photo evidence is the exact four-panel row PNG produced through the frozen
`scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py` renderer. The 199-building
driver changes membership only. The browser displays the copied PNG byte-for-byte and
must not compute or redraw a roofline.

The active assembly contract is `web_review199_exact_rows_v5.json`. It reserves 220 px
for the desktop photo row (170 px on narrow screens) and uses `object-fit: contain`, so
the exact PNG is scaled without cropping while preserving more vertical space for the
3D view. The image receives an explicit 210 px height (160 px on narrow screens),
preventing percentage-height resolution from overflowing behind the review controls.
Earlier exact-row configs are superseded display-only variants.

## Superseded paths retained for audit

`web_review199_photo_v1.json` through `web_review199_photo_v4.json` and the associated
external add-once packages used source JPEGs plus browser SVG overlays. They are not
active because that created a second projection/rendering implementation. They remain
available only for provenance and failure diagnosis; do not serve them as the current
review page.

The O/X localStorage key remains `jointbuildgs-c1-c2-roofer-ox-v1`, so replacing the
served package does not discard existing human review state. Scientific verdict is
`null`.
