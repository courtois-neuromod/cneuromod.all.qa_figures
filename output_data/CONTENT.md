# Output Data

Once the pipeline is run, this folder contains:

## Metric tables (from `invoke run-qc-measures`)

- `tables/{dataset}.tsv` — one row per functional run, with MRIQC
  image-quality metrics: `fd_mean`, `fd_num`, `fd_perc`, `tsnr`, `snr`,
  `gsr_x`, `gsr_y`, `dvars_std`, `dvars_vstd`, `aor`, `aqi`, `gcor`, `size_t`,
  plus `fd_prop_gt02` / `fd_prop_gt05` (proportion of volumes with FD > 0.2 / 0.5
  mm, from the MRIQC `*_timeseries.tsv` `framewise_displacement` column), and
  entities `dataset`, `subject`, `session`, `task`, `run`, `task_grouped`.

## Figures (from `invoke run-notebooks`)

- `figures/qc_measures/` — FD and tSNR raincloud distributions by subject and by
  task, and an FD-vs-tSNR scatter.

Each `figures/{notebook}/` folder also doubles as the notebook's "already ran"
sentinel used by `invoke run-notebooks`.

📝 Note: everything in this folder is **ignored by Git** (see `.gitignore`), so
outputs are not tracked.
