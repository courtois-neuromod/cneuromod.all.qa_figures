# Source Data

After `invoke fetch`, this folder contains:

* `cneuromod.all/` — the [CNeuroMod](https://www.cneuromod.ca/) `cneuromod.all`
  Datalad superdataset. It is either a **symlink** to an existing local checkout
  (default: `../cneuromod.all`, set via `source:` in `invoke.yaml` or
  `invoke fetch --source /path`) or a fresh **clone** of
  `https://github.com/courtois-neuromod/cneuromod.all` when no local checkout is
  available.

📝 File **content** inside the superdataset is retrieved selectively, never all
at once — the superdataset is large. `invoke fetch` installs each dataset's
`mriqc` subdataset and `datalad get`s only the small MRIQC text files the
pipeline reads (`*_bold.json`, `*_timeseries.tsv`); `*.nii.gz` and the large
fMRIPrep/bids content are never pulled. The analysis steps re-`datalad get` on
demand as a safety net.

📝 `cneuromod.all/` is **ignored by Git** here (see `.gitignore`), since it is an
external dataset with its own version control.
