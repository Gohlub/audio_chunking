## `hared` (import `shared.lib`)

Top-level **`shared/`** uv project (sibling of `benchmark/` and `pipeline/`).

- **`shared/src/shared/lib/`** — installable modules; import as **`shared.lib`** (async chunking, overlap merge, VAD)
- **`shared/animation/`** — Manim animation next to this tree. It is **not** part of the `shared` wheel or its dependencies; use `uv` / `requirements.txt` inside that folder only.
