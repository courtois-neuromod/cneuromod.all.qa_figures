"""Best-effort Datalad retrieval, tolerant of partial failures.

CNeuroMod data is only partly public — some participants (e.g. those without a
public-data agreement) make ``datalad get`` return errors for their files. Those
errors are expected: the pipeline retrieves whatever it can and skips the rest,
so a single inaccessible run never aborts a whole dataset.
"""

import subprocess
from pathlib import Path

# Some environments can reach github over HTTPS but not SSH, while the
# submodule URLs recorded in cneuromod.all are SSH (git@github.com:...). When a
# first attempt fails we retry once, rewriting SSH github URLs to HTTPS for that
# single invocation only (no persistent change to the user's git config).
_HTTPS_OVERRIDE = "url.https://github.com/.insteadOf=git@github.com:"


def _is_datalad_dataset(root):
    root = Path(root)
    return (root / ".datalad").is_dir() or (root / ".git").exists()


def _run(extra_config, args, cwd):
    cmd = ["datalad"]
    if extra_config:
        cmd += ["-c", extra_config]
    cmd += args
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def datalad_get(paths, dataset_root, recursive=False, get_content=True):
    """Run ``datalad get`` for ``paths`` (relative to ``dataset_root``).

    With ``get_content=False`` only the subdataset tree (filenames) is
    installed, not the annexed content. Never raises: on failure it retries once
    over HTTPS and, if that also fails, prints a warning and returns so the
    caller can proceed with whatever content is present.
    """
    root = Path(dataset_root)
    if not _is_datalad_dataset(root):
        return
    if isinstance(paths, (str, Path)):
        paths = [paths]
    args = ["get"]
    if not get_content:
        args.append("-n")
    if recursive:
        args.append("-r")
    args += [str(p) for p in paths]

    result = _run(None, args, root)
    if result.returncode != 0:
        result = _run(_HTTPS_OVERRIDE, args, root)
    if result.returncode != 0:
        preview = ", ".join(str(p) for p in paths[:2])
        print(f"⚠️  datalad get returned errors (continuing without): {preview} ...")


def install_subdataset(path, dataset_root):
    """Install the subdataset at ``path`` (relative to ``dataset_root``), no content.

    Runs ``datalad get -n`` rather than plain ``git submodule update --init``:
    each derivative of cneuromod.all (``{dataset}/{marker}``) is a Datalad
    subdataset nested *inside* the per-``{dataset}`` subdataset, and a plain
    ``git submodule`` cannot reach a submodule nested inside another submodule.
    Datalad installs the intermediate ``{dataset}`` subdataset and the nested
    ``{marker}`` in one call, leaving large sibling subdatasets like ``stimuli``
    untouched (non-recursive). Tolerant like ``datalad_get``: never raises, so an
    inaccessible derivative only warns and one dataset never aborts the whole run.
    """
    datalad_get(path, dataset_root, get_content=False)
