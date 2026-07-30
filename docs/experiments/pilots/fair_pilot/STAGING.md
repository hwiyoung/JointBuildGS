# fair-pilot staging boundary

This directory contains local, regenerable staging only. The immutable source
archive remains at `phases/p0-audit/data/raw/isprs/Vaihingen.zip`; the staging
script creates a relative symlink and selectively extracts the bounded Area 3
pilot subset. Nothing under this directory is committed.
