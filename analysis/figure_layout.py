"""Panel geometry read out of the hand-authored Inkscape montage.

`output_data/qa_figure.svg` is composed by hand and links each notebook panel
by relative path (`figures/qc_measures/fd_mean_by_dataset.png`, …). The box the
montage allocates to a panel is therefore the panel's true on-page size, and
this module exports those boxes so the notebooks can render each figure at
exactly that size (1:1, no rescaling at placement time). The SVG stays the
single source of truth for layout: resize a box in Inkscape and the next
`invoke run` regenerates that panel at the new size.

Tolerant by design — a missing or unparsable SVG yields an empty mapping rather
than breaking `invoke run` for someone who has not authored a montage yet.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

# SVG user units per millimetre, for the length units Inkscape may write.
_MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "px": 25.4 / 96}


def _length_in_mm(value):
    """Parse an SVG length such as ``208.26895mm`` into millimetres."""
    match = re.fullmatch(r"\s*([0-9.eE+-]+)\s*([a-z%]*)\s*", value or "")
    if not match:
        return None
    number, unit = match.groups()
    # A unitless length is in user units, which the viewBox then maps to mm.
    return float(number) * _MM_PER_UNIT.get(unit, 1.0)


def _mm_per_user_unit(root):
    """Millimetres per user unit, from the root width against its viewBox."""
    width_mm = _length_in_mm(root.get("width"))
    view_box = (root.get("viewBox") or "").replace(",", " ").split()
    if width_mm is None or len(view_box) != 4:
        return 1.0
    view_box_width = float(view_box[2])
    return width_mm / view_box_width if view_box_width else 1.0


def _transform_scale(transform):
    """Scale factors ``(sx, sy)`` of a transform attribute; translations are 1."""
    scale_x = scale_y = 1.0
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", transform or ""):
        values = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if name == "scale" and values:
            scale_x *= values[0]
            scale_y *= values[1] if len(values) > 1 else values[0]
        elif name == "matrix" and len(values) == 6:
            scale_x *= values[0]
            scale_y *= values[3]
    return scale_x, scale_y


def read_panel_sizes(svg_path):
    """Map each linked panel to the ``(width_mm, height_mm)`` box it is placed in.

    Keys are the panel's `xlink:href` with the leading `figures/` stripped, e.g.
    `qc_measures/fd_mean_by_dataset.png` — matching what a notebook writes under
    its own `figures/{notebook_stem}/` directory.
    """
    svg_path = Path(svg_path)
    if not svg_path.is_file():
        return {}
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError as error:
        print(f"warning: could not parse {svg_path}: {error}")
        return {}

    mm_per_unit = _mm_per_user_unit(root)
    parents = {child: parent for parent in root.iter() for child in parent}

    sizes = {}
    for image in root.iter(SVG_NS + "image"):
        href = image.get(XLINK_HREF) or image.get("href")
        width = _length_in_mm(image.get("width"))
        height = _length_in_mm(image.get("height"))
        if not href or width is None or height is None:
            continue
        # Ancestor layers currently carry translations only, which do not affect
        # size, but a re-save could wrap them in a scaled group (Inkscape's
        # px->mm matrix); fold any such scale in rather than silently ignore it.
        node = parents.get(image)
        while node is not None:
            scale_x, scale_y = _transform_scale(node.get("transform"))
            width *= scale_x
            height *= scale_y
            node = parents.get(node)
        key = href[len("figures/"):] if href.startswith("figures/") else href
        sizes[key] = (width * mm_per_unit, height * mm_per_unit)
    return sizes


def write_panel_sizes(svg_path, out_path):
    """Write `read_panel_sizes` to JSON for the notebooks to read. Returns the dict."""
    sizes = read_panel_sizes(svg_path)
    if not sizes:
        print(
            f"warning: no panel boxes found in {svg_path} — notebooks will fall "
            "back to their default figure sizes"
        )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sizes, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(sizes)} panel sizes to {out_path}")
    return sizes
