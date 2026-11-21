# a2_14_cell3_roofs

1-4: campus images that see the roof of at least one cell-3 building (46 buildings; building cell = the cell of most of its GT rows; sees = half of up to 200 roof sample points inside the image in front, occlusion not checked); training images in / not in the cell-3 list; coverage = share of the image covered by the projected cell-3 box (the 25 % rule)

scientific_verdict: null

| split | group | images | see_cell3_roof | in_cell3_list | missing | missing_coverage_median | missing_coverage_p90 |
|---|---|---|---|---|---|---|---|
| train | low_oblique | 495 | 82 | 31 | 51 | 0.108 | 0.187 |
| train | low_vertical | 26 | 0 | 0 | 0 | 없음 | 없음 |
| train | high_vertical | 298 | 142 | 142 | 0 | 없음 | 없음 |
| train | high_oblique | 0 | 0 | 0 | 0 | 없음 | 없음 |
| test | low_oblique | 71 | 12 | 없음 | 없음 | 없음 | 없음 |
| test | low_vertical | 4 | 0 | 없음 | 없음 | 없음 | 없음 |
| test | high_vertical | 43 | 21 | 없음 | 없음 | 없음 | 없음 |
| test | high_oblique | 0 | 0 | 없음 | 없음 | 없음 | 없음 |
