# Actual local viewer QA

Run after the final candidate seal, evaluation export and case figures exist:

```bash
bash scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.sh final_controls_v1 \
  'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_v2.json&qa_mode=full'
```

The wrapper preserves old QA runs and snapshots the executed script, wrapper and
viewer source. Use a fresh run ID. `qa_mode=preflight` permits explicitly pending
artifacts; it is also the default for `/viewer_preflight/` manifests. Every other
manifest defaults to full mode, which rejects pending candidates while allowing
explicit reconstruction failure, reference absence and recorded technical failure.

Full QA checks every registered resolution and condition, including
`native_repeat_1` when present, in raw and post mode against actual manifest
candidate IDs. It checks that 1024 anchor failures show their recorded reason
without falling back to 512, that the repeat uses the shared primary anchor,
and that resolution changes preserve the camera and recorded-case focus. It also
checks ALS mesh/points, synchronized recorded-case centers and metric extent,
section selection, and condition/domain/photo/comparison gallery filters. Empty
geometry is not required to become nonempty when an explicit failure is recorded.

Case and gallery selections are bounded and deterministic: up to three cases,
three section records, three render domains, two photos per domain and two
comparison figures per photo in each region. Selected case figures are additionally
checked when registered. The receipt records every filter/gallery/case checkpoint
and loaded image URL, selected resolution, actual candidate IDs and figure
comparison family; at most six screenshots per region are captured. This does
not claim inspection of every evaluation image or establish reconstruction quality.
When 512 is registered, the recorded-case screenshot uses that matched
anchor/refinement mode; the other geometry screenshots use the manifest default.
For each selected case, QA additionally checks up to two registered section
families and its first registered case render, using the exact recorded `case_id`.
Every case-figure declaration must reference an existing case and its condition.

Preparation validation only, without loading a browser or data:

```bash
docker run --rm --read-only --network none --cpus 1 --memory 512m \
  --mount "type=bind,src=$PWD/scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.mjs,dst=/qa/browser_qa.mjs,readonly" \
  jointbuildgs:geogs-viewer-browser-v2 --check /qa/browser_qa.mjs
```

Syntax validation is not an actual-viewer pass. The final browser command is
deferred until real regional evidence is ready.

The app's `resolution.mjs` is a pure helper for validating declared modes and
mapping surface candidate IDs. It does not inspect candidate availability to
choose a resolution. Include it with `viewer.js` in the final QA source snapshots.
