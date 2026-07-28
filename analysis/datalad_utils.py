"""Best-effort Datalad retrieval, tolerant of partial failures.

CNeuroMod data is only partly public — some participants (e.g. those without a
public-data agreement) make ``datalad get`` return errors for their files. Those
errors are expected: the pipeline retrieves whatever it can and skips the rest,
so a single inaccessible run never aborts a whole dataset.
"""

import os
import subprocess
from pathlib import Path

# Some environments can reach github over HTTPS but not SSH, while the
# submodule URLs recorded in cneuromod.all are SSH (git@github.com:...). When a
# first attempt fails we retry once, rewriting SSH github URLs to HTTPS for that
# single invocation only (no persistent change to the user's git config).
_HTTPS_OVERRIDE = "url.https://github.com/.insteadOf=git@github.com:"

# Some CNeuroMod content lives on credentialed SSH special remotes this
# environment has no key for. Left to their defaults, git/ssh fall back to an
# interactive password prompt — which reads from stdin and, with no TTY
# attached to a non-interactive subprocess, blocks forever instead of failing.
# Forcing batch mode (no prompts) plus a bounded connect timeout makes an
# unreachable/unauthorized remote fail fast like any other inaccessible
# content, instead of hanging the whole fetch indefinitely.
_NONINTERACTIVE_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_SSH_COMMAND": (
        os.environ.get("GIT_SSH_COMMAND", "ssh")
        + " -o BatchMode=yes -o ConnectTimeout=15"
    ),
}

# Hard backstop in case some other step (not git/ssh auth) still stalls —
# generous enough for a real bulk retrieval, short enough to not hang forever.
_SUBPROCESS_TIMEOUT_SECONDS = 600


def _is_datalad_dataset(root):
    root = Path(root)
    return (root / ".datalad").is_dir() or (root / ".git").exists()


def _run(extra_config, args, cwd):
    cmd = ["datalad"]
    if extra_config:
        cmd += ["-c", extra_config]
    cmd += args
    try:
        return subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            stdin=subprocess.DEVNULL, env=_NONINTERACTIVE_ENV,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            cmd, returncode=1, stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\ntimed out after {_SUBPROCESS_TIMEOUT_SECONDS}s",
        )


def datalad_get(paths, dataset_root, recursive=False, get_content=True,
                strict=False):
    """Run ``datalad get`` for ``paths`` (relative to ``dataset_root``).

    With ``get_content=False`` only the subdataset tree (filenames) is
    installed, not the annexed content. On failure it retries once over HTTPS.
    If that also fails: by default (tolerant) it prints a warning and returns so
    the caller can proceed with whatever content is present; with ``strict=True``
    it raises ``RuntimeError`` instead — used by the smoke test, which must fail
    loudly when retrieval does not work.
    """
    root = Path(dataset_root)
    if not _is_datalad_dataset(root):
        if strict:
            raise RuntimeError(f"{root} is not a Datalad dataset")
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
        if strict:
            raise RuntimeError(
                f"datalad get failed for {preview} ...\n{result.stderr.strip()}"
            )
        print(f"⚠️  datalad get returned errors (continuing without): {preview} ...")


def install_subdataset(path, dataset_root, strict=False):
    """Install the subdataset at ``path`` (relative to ``dataset_root``), no content.

    Runs ``datalad get -n`` rather than plain ``git submodule update --init``:
    each derivative of cneuromod.all (``{dataset}/{marker}``) is a Datalad
    subdataset nested *inside* the per-``{dataset}`` subdataset, and a plain
    ``git submodule`` cannot reach a submodule nested inside another submodule.
    Datalad installs the intermediate ``{dataset}`` subdataset and the nested
    ``{marker}`` in one call, leaving large sibling subdatasets like ``stimuli``
    untouched (non-recursive). By default tolerant like ``datalad_get`` (only
    warns), so an inaccessible derivative never aborts the whole run. With
    ``strict=True`` it raises if the subdataset is not actually installed
    afterwards (no ``.git`` at ``path``) — used by the smoke test.

    Skips the ``datalad`` subprocess entirely when the subdataset is already
    installed (``.git`` already present at ``path``) — on a repeat ``fetch``
    against an already-populated checkout this is the common case, and
    unconditionally re-invoking ``datalad get -n`` for every dataset/marker
    made every rerun pay full ``datalad`` startup/repo-scan overhead even when
    nothing had changed.
    """
    if (Path(dataset_root) / path / ".git").exists():
        return
    datalad_get(path, dataset_root, get_content=False, strict=strict)
    if strict and not (Path(dataset_root) / path / ".git").exists():
        raise RuntimeError(
            f"subdataset {path} was not installed (no .git at "
            f"{Path(dataset_root) / path})"
        )
