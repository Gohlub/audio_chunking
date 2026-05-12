# Merge overlap animation (Manim)

Self-contained scene next to **`../src/shared/lib/`** (same repo; not installed with `stt-shared`).

```bash
cd shared/animation
uv venv
uv pip install -r requirements.txt
```

## Render

```bash
source .venv/bin/activate
python -m manim -ql animation.py AnimationScene
```

## Modification
Experiment with different values by modifying `left_raw` and `right_raw` inside of `animation.py`. The layout is currently optimized for smaller experiments (5-6 word sentances), longer arguments will probably require some spacing adjustments.

Video output goes under `media/videos/` next to this file. Use Manim flags for quality and frame rate (for example `-qm`, `-qh`, `--fps 60`).
