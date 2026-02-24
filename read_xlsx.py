#!/usr/bin/env python3
"""Read and display CoirnaBot XLSX export files.

Usage:
    python read_xlsx.py                          # reads most recent file in xlsx/
    python read_xlsx.py xlsx/some_file.xlsx      # reads specific file
    python read_xlsx.py --sheet "Rolling Rankings"  # show specific sheet
    python read_xlsx.py --list                   # list all sheet names
"""

import argparse
import glob
import os
import sys

try:
    import openpyxl
except ImportError:
    print("Install openpyxl: pip install openpyxl")
    sys.exit(1)


def find_latest_xlsx(directory: str = "xlsx") -> str | None:
    """Find the most recently modified XLSX file in directory."""
    files = glob.glob(os.path.join(directory, "*.xlsx"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def print_sheet(ws, name: str, max_rows: int = 0) -> None:
    """Print a worksheet as a formatted table."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        print(f"\n=== {name} === (empty)")
        return

    headers = rows[0]
    data = rows[1:]
    if max_rows > 0:
        data = data[:max_rows]

    # Compute column widths
    col_widths = [len(str(h or "")) for h in headers]
    for row in data:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(val or "")))
    col_widths = [min(w, 25) for w in col_widths]  # cap at 25

    print(f"\n{'=' * 60}")
    print(f"  {name} ({len(data)} rows)")
    print(f"{'=' * 60}")

    # Header
    header_line = " | ".join(str(h or "").ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))

    # Data
    for row in data:
        parts = []
        for i, val in enumerate(row):
            if i >= len(col_widths):
                break
            s = str(val if val is not None else "")
            if len(s) > 25:
                s = s[:22] + "..."
            parts.append(s.ljust(col_widths[i]))
        print(" | ".join(parts))


def print_summary_sheet(ws) -> None:
    """Print the Summary sheet in a readable key-value format."""
    print(f"\n{'=' * 60}")
    print("  Summary")
    print(f"{'=' * 60}")
    for row in ws.iter_rows(values_only=True):
        vals = [v for v in row if v is not None]
        if not vals:
            print()
        elif len(vals) == 1:
            print(f"\n--- {vals[0]} ---")
        else:
            key = str(vals[0])
            val = vals[1] if len(vals) > 1 else ""
            if isinstance(val, float):
                val = f"{val:.6f}" if abs(val) < 1 else f"{val:.2f}"
            print(f"  {key:.<30s} {val}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read CoirnaBot XLSX exports")
    parser.add_argument("file", nargs="?", help="Path to XLSX file (default: latest in xlsx/)")
    parser.add_argument("--sheet", "-s", help="Show only this sheet")
    parser.add_argument("--list", "-l", action="store_true", help="List sheet names only")
    parser.add_argument("--rows", "-r", type=int, default=0, help="Max rows per sheet (0=all)")
    args = parser.parse_args()

    filepath = args.file or find_latest_xlsx()
    if not filepath or not os.path.exists(filepath):
        print("No XLSX file found. Export from dashboard first.")
        sys.exit(1)

    print(f"Reading: {filepath}")
    wb = openpyxl.load_workbook(filepath)

    if args.list:
        print(f"Sheets ({len(wb.sheetnames)}):")
        for name in wb.sheetnames:
            ws = wb[name]
            print(f"  - {name} ({ws.max_row - 1} rows)")
        return

    if args.sheet:
        if args.sheet in wb.sheetnames:
            ws = wb[args.sheet]
            if args.sheet == "Summary":
                print_summary_sheet(ws)
            else:
                print_sheet(ws, args.sheet, args.rows)
        else:
            print(f"Sheet '{args.sheet}' not found. Available: {wb.sheetnames}")
        return

    # Print all sheets
    for name in wb.sheetnames:
        ws = wb[name]
        if name == "Summary":
            print_summary_sheet(ws)
        else:
            print_sheet(ws, name, args.rows or 20)


if __name__ == "__main__":
    main()
