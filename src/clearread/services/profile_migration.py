"""One-time adoption of the pre-accounts data by the first profile on this machine.

Before v1.6 everything lived directly in the ClearRead folder. The first account that
signs in takes those files (moved, not copied); a marker stops any later account.
"""

import shutil
from pathlib import Path

from clearread.services.atomic_json import write_json_atomic

LEGACY_ITEMS = (
    "config.json",
    "glossary.json",
    "topics.json",
    "folders.json",
    "stats.json",
    "ai_cache.json",
    "cache",
)
ADOPTION_MARKER = "legacy_adopted.json"


def adopt_legacy_data(data_dir: Path, profile_dir: Path, uid: str) -> bool:
    """Move the legacy files into ``profile_dir``; True when this call adopted them.

    A failed move leaves the marker unwritten, so the next sign-in retries the rest.
    """
    marker = data_dir / ADOPTION_MARKER
    if marker.exists():
        return False
    if not _move_all(data_dir, profile_dir):
        return False
    write_json_atomic(marker, {"uid": uid})
    return True


def _move_all(data_dir: Path, profile_dir: Path) -> bool:
    profile_dir.mkdir(parents=True, exist_ok=True)
    complete = True
    for name in LEGACY_ITEMS:
        source = data_dir / name
        target = profile_dir / name
        if not source.exists() or target.exists():
            continue
        try:
            shutil.move(str(source), str(target))
        except OSError:
            complete = False
    return complete
