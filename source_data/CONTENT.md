# Source Data

After `invoke fetch`, this folder contains:

* `cneuromod.all/` — the [CNeuroMod](https://www.cneuromod.ca/) `cneuromod.all`
  Datalad superdataset. It is either a **symlink** to an existing local checkout
  (default: `../cneuromod.all`, set via `source:` in `invoke.yaml` or
  `invoke fetch --source /path`) or a fresh **clone** of
  `https://github.com/courtois-neuromod/cneuromod.all` when no local checkout is
  available.

📝 File **content** inside the superdataset (the small MRIQC BOLD JSONs) is
retrieved on demand by the analysis steps (`datalad get`), not all at once — the
superdataset is large.

📝 `cneuromod.all/` is **ignored by Git** here (see `.gitignore`), since it is an
external dataset with its own version control.
