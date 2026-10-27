# R12 issues

- First render attempt: Docker `/tmp` disallowed loading the compiled raster library (`failed to map segment from shared object`). No image was rendered. Store the task-local compiled library in the already writable R12 payload directory instead. Container resource limits and input mounts are unchanged.
- Existing MVS mesh is the already archived training-depth TSDF input surface, not a new GS run. Its holes and outlying triangles are retained; display quality must be judged separately from provenance verification.
- An audit launch was attempted before the render container had exited. Docker rejected the duplicate container name before execution. The render was left running; the audit is retried only after its completion.
