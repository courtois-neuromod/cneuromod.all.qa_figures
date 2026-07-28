"""Persistent record of files ``datalad get`` could not retrieve.

CNeuroMod data is only partly public: some files live solely on credentialed
special remotes (see ``analysis.datalad_utils``) that a given environment may
never be able to reach (no SSH key, no special-remote auth). Without a memory
of that, every ``invoke fetch`` re-attempts the exact same permanently
inaccessible files over the network — with connection timeouts and an HTTPS
retry on top, this is what makes a "just check for new files" fetch take
forever. This module records which files failed so the next fetch skips them
by default, and forgets a failure the moment that file is retried and
succeeds (e.g. access was later granted).
"""

import json
from pathlib import Path

_FAILURES_FILENAME = ".fetch_failures.json"


def _failures_path(source_data_dir):
    return Path(source_data_dir) / _FAILURES_FILENAME


def load_known_failures(source_data_dir):
    """Return the set of (root-relative) paths that previously failed to fetch."""
    path = _failures_path(source_data_dir)
    if not path.is_file():
        return set()
    return set(json.loads(path.read_text()))


def save_known_failures(source_data_dir, failures):
    """Persist the given set of (root-relative) paths as the known failures."""
    _failures_path(source_data_dir).write_text(
        json.dumps(sorted(failures), indent=2) + "\n"
    )
