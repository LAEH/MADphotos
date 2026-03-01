"""Layout validation for the bento system.

Checks every cell in every layout:
- Spans produce an allowed ratio
- No cell overlaps
- All cells within grid bounds
- Cell count matches

CLI: python3 -m backend.bento.validate
"""
from __future__ import annotations

from . import ALLOWED_SPANS
from .ratios import cell_ratio
from .layouts import ALL_LAYOUTS


def validate_layout(layout: dict) -> list[str]:
    """Validate a single layout. Returns list of error strings (empty = valid)."""
    errors: list[str] = []
    lid = layout.get("id", "?")
    cols = layout["cols"]
    rows = layout["rows"]
    cells = layout["cells"]

    if len(cells) != layout["count"]:
        errors.append(f"{lid}: count={layout['count']} but {len(cells)} cells defined")

    grid: set[tuple[int, int]] = set()
    total_area = 0

    for ci, cell in enumerate(cells):
        r, c, rs, cs = cell["r"], cell["c"], cell["rs"], cell["cs"]

        # Check spans are in allowed set
        if (rs, cs) not in ALLOWED_SPANS:
            ratio = cell_ratio(rs, cs)
            errors.append(f"{lid} cell[{ci}]: ({rs},{cs}) → ratio {ratio:.3f} NOT in ALLOWED_SPANS")

        # Check orient consistency
        expected_orient = 'P' if cs / rs < 1 else 'L'
        if cell["orient"] != expected_orient:
            errors.append(f"{lid} cell[{ci}]: orient='{cell['orient']}' but expected '{expected_orient}' for ({rs},{cs})")

        # Check bounds
        if r < 1 or c < 1:
            errors.append(f"{lid} cell[{ci}]: position ({r},{c}) out of bounds")
        if r + rs - 1 > rows:
            errors.append(f"{lid} cell[{ci}]: row {r}+{rs}-1={r+rs-1} exceeds grid rows={rows}")
        if c + cs - 1 > cols:
            errors.append(f"{lid} cell[{ci}]: col {c}+{cs}-1={c+cs-1} exceeds grid cols={cols}")

        # Check overlaps
        for dr in range(rs):
            for dc in range(cs):
                pos = (r + dr, c + dc)
                if pos in grid:
                    errors.append(f"{lid} cell[{ci}]: overlap at {pos}")
                grid.add(pos)
        total_area += rs * cs

    # Check total area covers the grid
    expected_area = cols * rows
    if total_area != expected_area:
        errors.append(f"{lid}: total area {total_area} ≠ grid area {expected_area}")

    return errors


def validate_all() -> list[str]:
    """Validate all layouts. Returns list of all errors."""
    all_errors: list[str] = []
    for layout in ALL_LAYOUTS:
        all_errors.extend(validate_layout(layout))
    return all_errors


def main():
    """CLI entry point."""
    errors = validate_all()
    total = len(ALL_LAYOUTS)

    if errors:
        print(f"FAIL — {len(errors)} errors in {total} layouts:\n")
        for e in errors:
            print(f"  ✗ {e}")
        raise SystemExit(1)
    else:
        print(f"OK — all {total} layouts valid ✓")

        # Print summary
        from .layouts import (
            DESKTOP_LAYOUTS, DESKTOP_SMALL_LAYOUTS,
            MOBILE_LAYOUTS, MOBILE_SMALL_LAYOUTS,
            DESKTOP_STARTER_LAYOUTS, MOBILE_STARTER_LAYOUTS,
        )
        print(f"  Desktop main:     {len(DESKTOP_LAYOUTS)}")
        print(f"  Desktop small:    {len(DESKTOP_SMALL_LAYOUTS)}")
        print(f"  Desktop starters: {len(DESKTOP_STARTER_LAYOUTS)}")
        print(f"  Mobile main:      {len(MOBILE_LAYOUTS)}")
        print(f"  Mobile small:     {len(MOBILE_SMALL_LAYOUTS)}")
        print(f"  Mobile starters:  {len(MOBILE_STARTER_LAYOUTS)}")


if __name__ == "__main__":
    main()
