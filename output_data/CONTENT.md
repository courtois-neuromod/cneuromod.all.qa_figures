# Output Data

Once the pipeline is run, this folder contains:

## Metric tables (from `invoke run-qc-measures` / `run-scans`)

- `qc_measures/{dataset}.tsv` — one row per functional run, with MRIQC
  image-quality metrics: `fd_mean`, `fd_num`, `fd_perc`, `tsnr`, `snr`,
  `gsr_x`, `gsr_y`, `dvars_std`, `dvars_vstd`, `aor`, `aqi`, `gcor`, `size_t`,
  plus entities `dataset`, `subject`, `session`, `task`, `run`, `task_grouped`.
- `scans/{dataset}.tsv` — aggregated BIDS `*_scans.tsv` rows (one per acquired
  file) with `acq_time` and the `dataset`, `subject`, `session`, `task`, `run`
  entities.

## Figures (from `invoke run-notebooks`)

- `figures/qc_measures/` — FD and tSNR raincloud distributions by subject and by
  task, and an FD-vs-tSNR scatter.
- `figures/scanning_timeline/` — session acquisition timeline and (when a
  duration column is available) scan-duration rainclouds.

Each `figures/{notebook}/` folder also doubles as the notebook's "already ran"
sentinel used by `invoke run-notebooks`.

📝 Note: everything in this folder is **ignored by Git** (see `.gitignore`), so
outputs are not tracked.
