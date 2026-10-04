"""Summary statistics of the QC tables, for quoting in prose.

Reads the per-run tables written by ``run-qc-measures``
(``tables/{dataset}.tsv``) and ``run-atlas-tsnr``
(``tables/atlas_tsnr/{dataset}.tsv``) and writes small summary tables to
``tables/summary/``, so a paper can quote every number without recomputing it:

- ``overall.tsv`` — one ``statistic``/``value`` row per scalar (run counts,
  FD and tSNR distributions, motion-outlier rates, FD-tSNR correlations).
- ``by_subject.tsv`` / ``by_dataset.tsv`` — run count and median FD / tSNR.
- ``by_region_group.tsv`` — median per-run tSNR of each atlas region group.
- ``coverage.tsv`` — per dataset, how many runs each analysis covers.

Every value is unrounded; formatting is the reader's job.
"""

from pathlib import Path

import pandas as pd

RUN_KEYS = ["dataset", "subject", "session", "task", "run"]
FD_MILD_MM = 0.2
FD_SEVERE_MM = 0.5


def _read_tables(folder):
    """{dataset: table} for every ``*.tsv`` in ``folder``; empty files give empty tables."""
    tables = {}
    for path in sorted(Path(folder).glob("*.tsv")):
        if path.stat().st_size > 2:
            tables[path.stem] = pd.read_csv(path, sep="\t", dtype={"subject": str})
        else:
            tables[path.stem] = pd.DataFrame(columns=RUN_KEYS)
    return tables


def _concat(tables):
    return pd.concat([t for t in tables.values() if len(t)], ignore_index=True)


def _distribution(values, prefix):
    return {
        f"{prefix}_median": values.median(),
        f"{prefix}_mean": values.mean(),
        f"{prefix}_sd": values.std(),
        f"{prefix}_min": values.min(),
        f"{prefix}_max": values.max(),
    }


def overall_statistics(runs):
    """Scalar summaries of the per-run MRIQC table."""
    fd = runs["fd_mean"].dropna()
    with_volumes = runs.dropna(subset=["fd_prop_gt02", "fd_prop_gt05"])
    paired = runs.dropna(subset=["fd_mean", "tsnr"])
    stats = {
        "n_runs": len(runs),
        "n_datasets": runs["dataset"].nunique(),
        "n_subjects": runs["subject"].nunique(),
        "n_sessions": runs.groupby(["dataset", "subject", "session"]).ngroups,
        **_distribution(fd, "fd"),
        "n_runs_fd_gt02": int((fd > FD_MILD_MM).sum()),
        "n_runs_fd_gt05": int((fd > FD_SEVERE_MM).sum()),
        "prop_runs_fd_gt02": (fd > FD_MILD_MM).mean(),
        "n_runs_with_fd_timeseries": len(with_volumes),
        "vol_prop_gt02_median": with_volumes["fd_prop_gt02"].median(),
        "vol_prop_gt05_median": with_volumes["fd_prop_gt05"].median(),
        "vol_prop_gt02_mean": with_volumes["fd_prop_gt02"].mean(),
        "vol_prop_gt05_mean": with_volumes["fd_prop_gt05"].mean(),
        **_distribution(runs["tsnr"].dropna(), "tsnr"),
        "fd_tsnr_pearson": paired["fd_mean"].corr(paired["tsnr"]),
        "fd_tsnr_spearman": paired["fd_mean"].corr(paired["tsnr"], method="spearman"),
    }
    return pd.DataFrame({"statistic": list(stats), "value": list(stats.values())})


def medians_by(runs, column):
    """Run count and median FD / tSNR per value of ``column``."""
    grouped = runs.groupby(column)
    return pd.DataFrame({
        "n_runs": grouped.size(),
        "fd_median": grouped["fd_mean"].median(),
        "tsnr_median": grouped["tsnr"].median(),
    }).reset_index()


def region_group_medians(region_runs):
    """Median per-run tSNR of each region group, lowest first."""
    grouped = region_runs.groupby("group")["tsnr_mean"]
    table = pd.DataFrame({"n_runs": grouped.size(), "tsnr_median": grouped.median()})
    return table.sort_values("tsnr_median").reset_index()


def coverage(qc_tables, region_tables):
    """Per dataset: runs with MRIQC metrics, runs and subjects with regional tSNR."""
    rows = []
    for dataset in sorted(set(qc_tables) | set(region_tables)):
        region = region_tables.get(dataset, pd.DataFrame(columns=RUN_KEYS))
        region_runs = region[RUN_KEYS].astype(str).drop_duplicates()
        rows.append({
            "dataset": dataset,
            "n_runs_mriqc": len(qc_tables.get(dataset, [])),
            "n_runs_region_tsnr": len(region_runs),
            "region_tsnr_subjects": ",".join(sorted(region_runs["subject"].unique())),
        })
    return pd.DataFrame(rows)


def summarize(output_dir):
    """Write the summary tables under ``{output_dir}/tables/summary/``."""
    tables_dir = Path(output_dir) / "tables"
    qc_tables = _read_tables(tables_dir)
    region_tables = _read_tables(tables_dir / "atlas_tsnr")
    runs = _concat(qc_tables)
    region_runs = _concat(region_tables)

    summary_dir = tables_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "overall": overall_statistics(runs),
        "by_subject": medians_by(runs, "subject"),
        "by_dataset": medians_by(runs, "dataset"),
        "by_region_group": region_group_medians(region_runs),
        "coverage": coverage(qc_tables, region_tables),
    }
    for name, table in outputs.items():
        table.to_csv(summary_dir / f"{name}.tsv", sep="\t", index=False)
    print(f"📊 Wrote {len(outputs)} summary tables to {summary_dir}")
