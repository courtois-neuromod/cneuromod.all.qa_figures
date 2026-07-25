from pathlib import Path

from invoke import task


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _cneuromod_dir(c):
    return Path(c.config.get("datasets", {}).get("cneuromod_all", {})["output_dir"])


def _select_datasets(requested, available, smoke):
    """Resolve which datasets a run task should process."""
    if requested:
        return [name.strip() for name in requested.split(",") if name.strip()]
    if smoke:
        return available[:1]
    return available


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
@task(help={
    "source": "Path to an existing local cneuromod.all checkout to use instead "
              "of cloning (defaults to the `source:` key in invoke.yaml, "
              "i.e. ../cneuromod.all).",
})
def fetch(c, source=None):
    """
    Make the cneuromod.all Datalad superdataset available under source_data/.

    Primary use case: symlink an existing local checkout (../cneuromod.all by
    default) so its content can be retrieved on demand by the analysis steps.
    When no local checkout exists, clone the remote superdataset instead. File
    content is NOT fetched here — the analysis steps `datalad get` only the small
    text files (MRIQC JSONs, scans.tsv) they need.
    """
    cfg = c.config.get("datasets", {}).get("cneuromod_all", {})
    dest = Path(cfg["output_dir"])
    url = cfg.get("url")
    source = source or cfg.get("source")

    if dest.exists() or dest.is_symlink():
        print(f"🫧 Skipping cneuromod.all — already present at {dest}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    if source and Path(source).exists():
        target = Path(source).resolve()
        print(f"🔗 Linking existing checkout {target} -> {dest}")
        dest.symlink_to(target, target_is_directory=True)
    else:
        if source:
            print(f"⚠️  Source '{source}' not found — cloning remote instead.")
        print(f"📥 Cloning {url} -> {dest} (content retrieved on demand)")
        c.run(f"datalad clone {url} {dest}")

    print("✅ fetch complete.")


# --------------------------------------------------------------------------- #
# Analysis steps (chunk = dataset)
# --------------------------------------------------------------------------- #
@task(help={
    "datasets": "Comma-separated dataset names to process (default: all with an "
                "mriqc subdataset).",
    "smoke": "Process only the first dataset (fast end-to-end check).",
})
def run_qc_measures(c, datasets=None, smoke=False):
    """
    Extract per-run MRIQC QC metrics for each dataset of cneuromod.all.

    Writes one tidy table per dataset to output_data/qc_measures/{dataset}.tsv.
    Datasets whose output already exists are skipped.
    """
    from analysis.datasets import list_datasets
    from analysis.qc_measures import extract_qc_measures

    cneuromod_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    names = _select_datasets(datasets, list_datasets(cneuromod_dir, "mriqc"), smoke)

    for dataset in names:
        out = output_dir / "qc_measures" / f"{dataset}.tsv"
        if out.exists():
            print(f"🫧 Skipping {dataset} qc_measures (output exists)")
            continue
        extract_qc_measures(dataset, cneuromod_dir, output_dir, smoke=smoke)


@task(help={
    "datasets": "Comma-separated dataset names to process (default: all with a "
                "bids subdataset).",
    "smoke": "Process only the first dataset (fast end-to-end check).",
})
def run_scans(c, datasets=None, smoke=False):
    """
    Aggregate BIDS *_scans.tsv into a scanning table for each dataset.

    Writes one table per dataset to output_data/scans/{dataset}.tsv. Datasets
    whose output already exists are skipped.
    """
    from analysis.datasets import list_datasets
    from analysis.scans import aggregate_scans

    cneuromod_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    names = _select_datasets(datasets, list_datasets(cneuromod_dir, "bids"), smoke)

    for dataset in names:
        out = output_dir / "scans" / f"{dataset}.tsv"
        if out.exists():
            print(f"🫧 Skipping {dataset} scans (output exists)")
            continue
        aggregate_scans(dataset, cneuromod_dir, output_dir, smoke=smoke)


# --------------------------------------------------------------------------- #
# Notebooks
# --------------------------------------------------------------------------- #
@task
def run_notebooks(c):
    """
    Generate QA figures from the metric tables in output_data/ using notebooks.
    """
    from airoh.utils import ensure_dir_exist
    from airoh.utils import run_notebooks as airoh_run_notebooks

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    figures_base = Path(c.config.get("figures_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    # Each notebook writes into figures_base/<stem>/, which airoh also treats as
    # the per-notebook "already ran" sentinel — kept separate from the data dirs
    # output_data/qc_measures/ and output_data/scans/.
    airoh_run_notebooks(
        c, notebooks_dir, figures_base, keys=["source_data_dir", "output_data_dir"]
    )


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
@task(pre=[fetch, run_qc_measures, run_scans, run_notebooks])
def run(c):
    """Full pipeline: fetch → qc-measures → scans → figures."""
    print("all analyses completed")


@task
def run_smoke(c):
    """Smoke test: minimal end-to-end pass (first dataset only)."""
    fetch(c)
    run_qc_measures(c, smoke=True)
    run_scans(c, smoke=True)
    run_notebooks(c)


# --------------------------------------------------------------------------- #
# Clean
# --------------------------------------------------------------------------- #
@task
def clean_qc_measures(c):
    """Remove QC-metric outputs."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "qc_measures/*.tsv")


@task
def clean_scans(c):
    """Remove aggregated scans outputs."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "scans/*.tsv")


@task
def clean_figures(c):
    """Remove generated figures and notebook sentinels."""
    from airoh.utils import clean_folder
    clean_folder(c, "figures_dir")


@task(pre=[clean_qc_measures, clean_scans, clean_figures])
def clean(c):
    """Remove all computed outputs."""
    pass


@task
def clean_cneuromod(c):
    """Remove the fetched cneuromod.all superdataset (symlink or clone)."""
    dest = _cneuromod_dir(c)
    if dest.is_symlink():
        dest.unlink()
        print(f"🧹 Removed symlink {dest}")
    elif dest.exists():
        print(f"⚠️  {dest} is a real clone, not a symlink — remove it manually "
              f"if you are sure: rm -rf {dest}")
    else:
        print(f"🫧 Nothing to clean — {dest} is not present")


@task(pre=[clean_cneuromod])
def clean_source(c):
    """Remove all fetched source data."""
    pass
