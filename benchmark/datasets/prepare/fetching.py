"""
Download and zip-extraction helpers shared by dataset ``prepare`` modules.

Used by AMI/ICSI to fetch annotation zips and source audio, and by Earnings22 to fetch ``.mp3``
and ``.nlp`` files. Nothing in here knows about a specific corpus.
"""
from __future__ import annotations

import shutil
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

CHUNK_BYTES = 8 * 1024 * 1024


def download_file(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    user_agent: str = "STT-exploration-fetch/1.0",
) -> None:
    """Stream ``url`` to ``dest``. Skips if ``dest`` already exists and is non-empty unless ``force``."""
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"skip (exists): {dest}")
        return
    print(f"fetch: {url}")
    print(f"  -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            tmp = dest.with_suffix(dest.suffix + ".part")
            try:
                with tmp.open("wb") as out:
                    while True:
                        block = resp.read(CHUNK_BYTES)
                        if not block:
                            break
                        out.write(block)
                tmp.replace(dest)
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP error {e.code} for {url}") from e


def has_word_layer(path: Path) -> bool:
    """True if ``path/words/*.words.xml`` exists (AMI / ICSI manual annotation shape)."""
    w = path / "words"
    return w.is_dir() and any(w.glob("*.words.xml"))


def ensure_words_layer(
    cache_root: Path,
    *,
    nested_dir_name: str,
    zip_name: str,
    zip_url: str,
    force: bool = False,
    user_agent: str = "STT-exploration-fetch/1.0",
    after_extract: Callable[[Path], None] | None = None,
) -> Path:
    """Download (if needed) and unzip an annotation archive into ``cache_root/<nested_dir_name>``."""
    nested = cache_root / nested_dir_name
    if not force and has_word_layer(nested):
        print(f"skip extract (has words): {nested}")
        return nested

    if force and nested.exists():
        shutil.rmtree(nested)

    zip_path = cache_root / zip_name
    if not zip_path.exists() or zip_path.stat().st_size == 0 or force:
        download_file(zip_url, zip_path, force=force, user_agent=user_agent)

    print(f"extract: {zip_path} -> {nested}")
    nested.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(nested)
    if after_extract is not None:
        after_extract(nested)

    if not has_word_layer(nested):
        raise SystemExit(f"no words/ with *.words.xml after unzip; expected: {nested / 'words'}")
    return nested


def require_option(value: str | None, flag_name: str, env_name: str) -> str:
    if value:
        return value
    raise SystemExit(f"missing {flag_name}: pass {flag_name} or set {env_name} in the environment")
