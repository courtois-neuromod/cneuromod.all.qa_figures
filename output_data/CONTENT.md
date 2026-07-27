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
  dataset, and an FD-vs-tSNR scatter.
- `figures/tsnr_maps/` — axial volumetric montages of the average tSNR maps: one
  per dataset (`{dataset}_avgtsnr.png`) and one per subject
  (`{dataset}_sub-XX_avgtsnr.png`), on a shared colour scale. Rendered directly
  from the upstream per-subject `stat-avgtsnr` maps in
  `source_data/cneuromod.all/{dataset}/tsnr/`; the dataset-average is computed
  in memory by the notebook (each subject resampled to a common grid,
  `np.nanmean`) — no NIfTI is written here or anywhere under `output_data/`.
- `figures/motion_bands/` — stacked bars of the per-run motion budget (% low
  FD ≤ 0.2, moderate 0.2–0.5, high > 0.5 mm), averaged over runs:
  `motion_bands_by_dataset_subject.png` (one panel per dataset, one bar per
  subject) and `motion_bands_grand_average.png` (one bar per subject, averaged
  across all datasets with each dataset weighted equally).

Each `figures/{notebook}/` folder also doubles as the notebook's "already ran"
sentinel used by `invoke run-notebooks`.

📝 Note: `tables/` and `figures/` (plus `qa_figure.png`/`qa_figure.svg`) are
**tracked in Git** — no NIfTI is stored here, so these outputs stay small and
diffable.
