"""House figure style, shared by every QA notebook.

Lives next to the notebooks rather than in `analysis/` because nbconvert runs
them with `notebooks/` as the cwd, so the `analysis` package is not importable
there — the same constraint that makes `tsnr_maps.ipynb` duplicate its `SPACE`
constants. A plain sibling module sidesteps it.

The palette and `style_axes` chrome used to be copy-pasted into three
notebooks; this module is the one place they're defined, plus a font scale
sized for the final page rather than for a screen.

On-page panel sizing (`panel_size`, `MM_PER_INCH`) now lives in
`airoh.figures`, re-exported below for the notebooks' existing `panel()`
helpers. That module returns the physical box the hand-authored Inkscape
montage (`output_data/qa_figure.svg`) allocates to a panel, read from the
`panel_sizes.json` that `invoke run-figure-layout` writes, so a panel renders
at exactly the size it is placed at and its text is never stretched.

Two rules go with that and must be kept: save at `PAGE_DPI`, and never pass
`bbox_inches="tight"` — tight cropping resizes the canvas after the fact, which
is precisely what made the saved size unpredictable. Use `layout="constrained"`
instead to reclaim margins inside the fixed canvas.
"""

import matplotlib.pyplot as plt
from airoh.figures import MM_PER_INCH, panel_size  # noqa: F401
from matplotlib.patches import Rectangle

# --- House figure style (dataviz skill) --------------------------------------
# Colour is assigned by the job it does and checked with the skill's validator:
#   * per-run distributions are already labelled on the x-axis, so the marks use
#     ONE recessive hue instead of a decorative rainbow;
#   * the motion-band severity scale uses the reserved status colours
#     (good / warning / critical), CVD-checked as an ordered, gap-separated stack.
HUE = "#2a78d6"      # single categorical hue (blue, slot 1)
INK = "#0b0b0b"      # primary ink
MUTED = "#898781"    # axis + tick labels (recessive)
GRID = "#e1e0d9"     # hairline gridline

# Departure from the single-hue convention above: colour here does a real job
# — linking each of the nine region-group violins in atlas_tsnr.ipynb to its
# glass-brain map by identity across two panels — which is exactly when the
# dataviz skill calls for categorical hue. This is a fixed *domain* palette (one
# entry per named category, assigned in a fixed order, never cycled), not a
# decorative rainbow. The 7 Yeo-7 network colors are the canonical literature
# values; Cerebellum/Central structures get two off-palette colors since they
# aren't Yeo networks. Canonical Yeo Limbic (#DCF8A4) is near-invisible on a
# white glass-brain background and low-contrast as a violin fill, so it is
# darkened here for legibility.
GROUP_COLORS = {
    "Vis":         "#781286",  # Yeo visual (purple)
    "SomMot":      "#4682B4",  # Yeo somatomotor (steel blue)
    "DorsAttn":    "#00760E",  # Yeo dorsal attention (green)
    "SalVentAttn": "#C43AFA",  # Yeo ventral attention / salience (violet)
    "Limbic":      "#B5B54E",  # Yeo limbic, darkened from #DCF8A4 for legibility
    "Cont":        "#E69422",  # Yeo frontoparietal control (orange)
    "Default":     "#CD3E4E",  # Yeo default mode (red)
    "Cerebellum":  "#2E8B8B",  # off-palette teal (not a Yeo network)
    "Central structures": "#8B5E3C",  # off-palette brown
}

# Panels are placed in the montage at 1:1, so a point here is a point on the
# page. Sized against the Inkscape-authored text it sits next to (12 pt panel
# letters, 10 pt titles, 8 pt annotations): axis labels read just below those.
# Keep y-axis labels terse ("FD (mm)", not "Mean FD (mm)"): the placed panels
# are only ~30 mm tall, and a rotated label longer than the axes is silently
# clipped at the figure edge — constrained layout cannot shrink a fixed canvas.
PAGE_DPI = 300
FONT_SIZES = {
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 9,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
}

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "font.family": "sans-serif",
    # Chrome thinned for the small on-page format: at ~1 inch of panel height
    # the previous 0.8 pt spines and long ticks read as heavy furniture.
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 2,
    "ytick.major.size": 2,
    "figure.dpi": PAGE_DPI,
    "savefig.dpi": PAGE_DPI,
    **FONT_SIZES,
})


def style_axes(ax):
    """Recessive chrome: drop top/right spines, hairline y-grid, ticks behind."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, color=GRID, linewidth=0.4)
    ax.set_axisbelow(True)
    return ax


def overlay_median_iqr(ax, data, x, y, order, width=0.08, offset=0.02, color=None):
    """Draw a median line + open IQR box (no whiskers, caps, or fliers) per category.

    A first attempt at showing median/decile numbers as text over each cloud
    (two decimals x three stats x every category) was too heavy for these
    ~1-inch-tall panels. An open box reads the same two numbers (median,
    Q1-Q3) as a shape instead of digits, so it costs far less ink. `raincloud`
    in both notebooks pushes the half-violin left (`offset=-.15`) and the
    jittered strip right (`move=.3`) beyond their original spacing precisely
    to open a clear gap for this narrow box to sit in, touching neither.
    """
    color = INK if color is None else color
    quantiles = data.groupby(x)[y].quantile([.25, .5, .75]).unstack()
    for position, category in enumerate(order):
        if category not in quantiles.index:
            continue
        q1, median, q3 = quantiles.loc[category, [0.25, 0.5, 0.75]]
        left = position + offset - width / 2
        ax.add_patch(Rectangle((left, q1), width, q3 - q1, fill=False,
                                edgecolor=color, linewidth=.6, zorder=5))
        ax.hlines(median, left, left + width, color=color, linewidth=1.0,
                  zorder=6)
    return ax


def montage_font_sizes(width_in, reference_in=4.13):
    """`(annotation, title)` point sizes for a nilearn montage of this width.

    The placed montages are ~4.13 in wide — a 5.5x linear reduction from
    nilearn's default figure — so their `L`/`R`/`z=` annotations have to shrink
    with them. The unplaced per-subject/sagittal/coronal montages stay large, so
    the size scales with the figure rather than being a constant, capped at
    nilearn's own defaults so those panels look unchanged.

    Title and annotation converge at page scale: nilearn draws the title in an
    opaque box whose width follows the font, and at 4 inches a title 25% larger
    than the annotations covers enough of the first slice to hide anything
    annotated over it.
    """
    scale = width_in / reference_in
    annotation = min(12.0, max(4.0, 4.0 * scale))
    return (annotation, min(15.0, max(4.0, 5.0 * scale)))
