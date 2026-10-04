"""Enable the S3 and public-HTTP special remotes of an installed subdataset.

A subdataset's S3 special remotes are mostly recorded ``autoenable=true`` in
``remote.log``, but git-annex only acts on that at ``git annex init`` (i.e. at
install time). A checkout installed before the remotes were added to the
``git-annex`` branch, or one whose branch was later merged forward, keeps them
disabled; a fresh direct install enables them on its own (verified, with or
without credentials). A later ``git annex get`` then finds no remote holding the
content and reports it "not available" without ever contacting S3. ``fetch``
therefore enables them explicitly after installing each subdataset, so existing
and fresh checkouts behave alike (the exact cause for a given stale checkout —
older install vs. nested install via the superdataset — is not established).

The public ``httpalso`` remote (``conp-ria-storage-http``: HTTPS view of the CONP
RIA store, no credentials, no SSH tunnel) is the one that actually serves
content for datasets like ``hcptrt/tsnr``, whose S3 bucket refuses reads
(``403``) for some accounts; it is ``autoenable=true`` and a fresh install gets it
for free, but an older checkout may lack it.

Remotes are picked by *type* (``S3`` or ``httpalso`` in the ``git-annex`` branch's
``remote.log``) and only those the maintainers marked ``autoenable=true`` — the
same set a fresh install enables, so nothing is switched on that they left off —
not by name: the naming is not consistent across subdatasets
(``s3unf.cneuromod.hcptrt.mri`` but ``unfs3.cneuromod.hcptrt.tsnr``). Anything
named ``sensitive`` is never enabled (restricted-data buckets), and RIA/SSH
remotes are left alone since they need accounts on other machines.
"""

import subprocess
from pathlib import Path

REMOTE_LOG_REF = "git-annex:remote.log"
SENSITIVE_MARKER = "sensitive"
ENABLEABLE_TYPES = ("S3", "httpalso")


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=120,
    )


def list_enableable_remote_names(repo):
    """Names of the ``autoenable=true`` S3 / httpalso remotes in ``repo``'s remote.log.

    ``httpalso`` entries (the public HTTP view of a RIA store, no credentials
    needed) carry their name in ``sameas-name=`` rather than ``name=``.
    """
    result = _git(repo, "show", REMOTE_LOG_REF)
    if result.returncode != 0:
        return []
    names = []
    for line in result.stdout.splitlines():
        fields = dict(f.split("=", 1) for f in line.split()[1:] if "=" in f)
        name = fields.get("name") or fields.get("sameas-name")
        autoenabled = fields.get("autoenable") == "true"
        if fields.get("type") in ENABLEABLE_TYPES and name and autoenabled:
            names.append(name)
    return names


def _is_enabled(repo, name):
    return _git(repo, "config", "--get", f"remote.{name}.annex-uuid").returncode == 0


def enable_public_and_s3_remotes(repo, strict=False):
    """Run ``git annex enableremote`` for each not-yet-enabled, non-sensitive S3/httpalso remote.

    Idempotent: already-enabled remotes are skipped. Returns the names newly
    enabled. Tolerant by default — a remote that cannot be enabled (typically
    ``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY`` unset) only warns, so the
    gather proceeds with whatever content is reachable; ``strict=True`` raises.
    """
    repo = Path(repo)
    if not (repo / ".git").exists():
        return []
    enabled = []
    for name in list_enableable_remote_names(repo):
        if SENSITIVE_MARKER in name or _is_enabled(repo, name):
            continue
        result = subprocess.run(
            ["git", "annex", "enableremote", name], cwd=str(repo),
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
        )
        if result.returncode == 0:
            print(f"🪣 enabled remote {name} in {repo.name}")
            enabled.append(name)
            continue
        message = f"could not enable remote {name} in {repo}: {result.stderr.strip()}"
        if strict:
            raise RuntimeError(message)
        print(f"⚠️  {message} (are AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY set?)")
    return enabled
