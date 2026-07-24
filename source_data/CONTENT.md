After `invoke fetch` is complete, expect the following content:
 * `YNIMG_BrainParcellation_summary.tsv` - a spreadsheet with some data on a series of articles.

📝 Note: tsv files are **ignored by Git** (see `.gitignore`), so data assets won't be tracked by default.

📝 Note: assets here may be **symlinks** to data that already lives elsewhere on disk, rather than local copies — this happens when a fetch task is run with `--source` (e.g. `invoke fetch-papers --source /path`, or `invoke fetch --papers-source /path`), or a `source:` key is set in `invoke.yaml`.


