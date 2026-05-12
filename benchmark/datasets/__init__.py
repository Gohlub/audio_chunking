"""
Dataset registry and preparation dispatcher.

Each dataset lives in its own subpackage with two files:

  datasets/<name>/prepare.py      - downloads source media, normalizes to FLAC, writes references
  datasets/<name>/transcripts.py  - parses corpus-native annotations into BenchmarkCase records

Adding a dataset = create the subpackage and add a one-line entry to ``_DATASETS`` below. The
shared flow (download -> normalize-to-FLAC -> write benchmark refs) lives under
``datasets.prepare`` (``cases``, ``fetching``, ``normalization``, ``paths``, ``word_xml``) and is
small enough to read in one sitting.

See ``datasets/README.md`` for what each registered dataset actually contains, and
``datasets/CLANKER.md`` for the agent guide on adding a new one.

CLI entry point: ``data/prepare_dataset.py``.
"""
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator, Sequence

_DATASETS: dict[str, str] = {
    "ami": "AMI: licence + Mix-Headset audio + word XML -> FLAC + .ref / .hyp",
    "icsi": "ICSI: licence + interaction audio + word XML -> FLAC + .ref / .hyp",
    "earnings22": "Earnings22: Rev MP3 + .nlp -> FLAC + .ref / .hyp",
}

# Each prepare module exposes a tuple of default case ids under one of these names.
_DEFAULT_ATTRS: tuple[str, ...] = ("DEFAULT_MEETINGS", "DEFAULT_FILE_IDS", "DEFAULT_CASE_IDS")


def list_dataset_ids() -> list[str]:
    return sorted(_DATASETS)


def iter_dataset_entries() -> Iterator[tuple[str, str]]:
    for k in list_dataset_ids():
        yield k, _DATASETS[k]


def _prepare_module(name: str):
    if name not in _DATASETS:
        known = ", ".join(list_dataset_ids())
        raise KeyError(f"unknown dataset {name!r}; one of: {known}")
    return importlib.import_module(f"{__name__}.{name}.prepare")


def _main_for(name: str) -> Callable[[Sequence[str] | None], int]:
    return _prepare_module(name).main


def default_case_ids(name: str) -> list[str]:
    """Return the dataset's default case ids (meeting / file ids), as defined in its prepare module."""
    mod = _prepare_module(name)
    for attr in _DEFAULT_ATTRS:
        v = getattr(mod, attr, None)
        if v is not None:
            return list(v)
    raise AttributeError(
        f"datasets.{name}.prepare must expose one of {_DEFAULT_ATTRS} for default case ids"
    )


def run_prepare(name: str, argv: list[str] | None = None) -> int:
    """Prepare one dataset by id, forwarding ``argv`` to its CLI."""
    return _main_for(name)(list(argv) if argv is not None else [])


def prepare_all() -> int:
    """Prepare every registered dataset in id order, with each script's defaults."""
    for i, name in enumerate(list_dataset_ids()):
        if i:
            print(f"\n{'=' * 60}\n", flush=True)
        print(f">>> prepare: {name}\n", flush=True)
        rc = run_prepare(name, [])
        if rc != 0:
            return rc
    return 0


def _print_help(stream=sys.stderr) -> None:
    w = max((len(k) for k in list_dataset_ids()), default=0)
    print("usage: prepare_dataset.py {list|all|<id>} [args…]", file=stream)
    print("  list   show this help", file=stream)
    print("  all    run every dataset (default args for each)", file=stream)
    print("  <id>   run that corpus only; extra args go to its prepare script", file=stream)
    print("\ndatasets:", file=stream)
    for did, desc in iter_dataset_entries():
        print(f"  {did:{w}}  {desc}", file=stream)


def main_cli() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "list"):
        _print_help(sys.stdout if sys.argv[1:2] == ["list"] else sys.stderr)
        return 0 if sys.argv[1:2] in (["-h"], ["--help"], ["list"]) else 1
    if sys.argv[1] == "all":
        if len(sys.argv) > 2:
            print("prepare_dataset.py all: takes no extra args (run each <id> separately for flags).", file=sys.stderr)
            return 1
        return prepare_all()
    try:
        return run_prepare(sys.argv[1], sys.argv[2:])
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1
