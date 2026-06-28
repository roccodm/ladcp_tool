#!/usr/bin/env python3
"""
ctd_tool — Process SBE CTD .cnv files with GSW.

Reads Sea-Bird .cnv files (from DatCnv or later SBE processing),
computes derived variables using GSW, bins to pressure grid,
and outputs: ASCII profiles, publication-quality plots, ODV spreadsheets.

Usage:
    ctd_tool --source-dir ./02-CTD-processed --output-dir ./ctd_output
    ctd_tool --source-dir ./02-CTD-processed --output-dir ./ctd_output --bin-size 2
"""

import sys
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

# Add parent to path for ladcp_tool imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ladcp_tool.processors.ctd_processor import (
    read_cnv, extract_ctd, compute_derived, bin_profile, save_ldeo_format,
    isolate_downcast, check_pressure_monotonicity,
)
from ladcp_tool.outputs.odv_writer import write_odv_collection
from ladcp_tool.outputs.plotter import plot_ctd_profile, plot_combined
from ladcp_tool.outputs.result_writer import write_summary


def main():
    parser = argparse.ArgumentParser(
        description="ctd_tool — Process SBE CTD .cnv files with GSW derived variables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ctd_tool -s ./CTD-processed -o ./ctd_out
  ctd_tool -s ./CTD-processed -o ./ctd_out --bin-size 2
  ctd_tool -s ./CTD-processed -o ./ctd_out --no-plots
""")
    
    parser.add_argument('-s', '--source-dir', required=True,
                        help='Directory with .cnv files (e.g., 07-LoopEdit output)')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for results, plots, ODV files')
    parser.add_argument('--bin-size', type=float, default=1.0,
                        help='Pressure bin size for profiles (dbar, default: 1)')
    parser.add_argument('--cruise-id', default='TUNSIC26',
                        help='Cruise identifier (default: TUNSIC26)')
    parser.add_argument('--no-plots', action='store_true',
                        help='Skip plot generation')
    parser.add_argument('--no-odv', action='store_true',
                        help='Skip ODV file generation')
    parser.add_argument('--no-ldeo', action='store_true',
                        help='Skip LDEO-compatible ASCII output')
    parser.add_argument('--include-upcast', action='store_true',
                        help='Include upcast data in profiles (default: downcast only)')
    
    args = parser.parse_args()
    
    source = Path(args.source_dir)
    output = Path(args.output_dir)
    
    if not source.exists():
        print(f"ERROR: Source directory not found: {source}")
        sys.exit(1)
    
    # Create output structure
    res_dir = output / "results"
    plot_dir = output / "plots"
    odv_dir = output / "odv"
    ldeo_dir = output / "ldeo_ascii"
    
    for d in [res_dir, plot_dir, odv_dir, ldeo_dir]:
        d.mkdir(exist_ok=True, parents=True)
    
    print(f"{'='*60}")
    print(f"  ctd_tool — CTD Processing with GSW")
    print(f"  Source: {source}")
    print(f"  Output: {output}")
    print(f"  Bin size: {args.bin_size} dbar")
    print(f"  Mode: {'downcast + upcast' if args.include_upcast else 'downcast only'}")
    print(f"{'='*60}\n")
    
    cnv_files = sorted(source.glob("*.cnv"))
    if not cnv_files:
        print(f"ERROR: No .cnv files found in {source}")
        sys.exit(1)
    
    print(f"Found {len(cnv_files)} .cnv file(s)\n")
    
    all_casts = []
    
    for cnv_file in cnv_files:
        # Derive cast ID from filename
        cast_id = cnv_file.stem.replace("TUNSIC", "")
        print(f"Processing {cast_id}...")
        
        try:
            arr, meta = read_cnv(cnv_file)
            ctd_raw = extract_ctd(arr, meta)
            
            if ctd_raw is None:
                print(f"  SKIP: missing P/T/C columns")
                continue

            if not args.include_upcast:
                n_before = len(ctd_raw['pressure'])
                ctd_raw = isolate_downcast(ctd_raw)
                pct = 100 * ctd_raw['n_scans_downcast'] / max(ctd_raw['n_scans_raw'], 1)
                p_lo = float(np.nanmin(ctd_raw['pressure'])) if len(ctd_raw['pressure']) else 0.0
                p_hi = float(np.nanmax(ctd_raw['pressure'])) if len(ctd_raw['pressure']) else 0.0
                print(f"  Downcast: {ctd_raw['n_scans_downcast']}/{ctd_raw['n_scans_raw']}"
                      f" scan ({pct:.0f}%)")
                print(f"  Pressure range: {p_lo:.1f} – {p_hi:.1f} dbar")
                if ctd_raw.get('monotonicity_violations', 0) > 0:
                    print(f"  Monotonicity violations removed: "
                          f"{ctd_raw['monotonicity_violations']} scans")

            derived = compute_derived(ctd_raw)
            binned = bin_profile(ctd_raw, derived, bin_size=args.bin_size)
            
            n_levels = len(binned['depth'])
            max_depth = np.nanmax(binned['depth'])
            print(f"  Profile: {n_levels} levels, max depth {max_depth:.0f} m")
            print(f"  T range: [{np.nanmin(binned['temperature']):.2f}, "
                  f"{np.nanmax(binned['temperature']):.2f}] °C")
            print(f"  S range: [{np.nanmin(binned['salinity']):.2f}, "
                  f"{np.nanmax(binned['salinity']):.2f}] PSU")
            
            # Save results
            result_file = res_dir / f"{cast_id}_ctd_profile.txt"
            header = f"# CTD Profile — Cast {cast_id} — GSW-derived\n"
            header += f"# {'P(dbar)':>8s} {'Depth(m)':>8s} {'T(°C)':>8s} {'S(PSU)':>8s} "
            header += f"{'σ₀':>8s} {'ρ(kg/m³)':>10s} {'SS(m/s)':>8s} {'θ(°C)':>8s}\n"
            np.savetxt(result_file, np.column_stack([
                binned['pressure'], binned['depth'], binned['temperature'],
                binned['salinity'], binned['sigma0'], binned['density'],
                binned['sound_speed'], binned['pot_temp'],
            ]), fmt='%8.2f %8.1f %8.4f %8.4f %8.4f %10.4f %8.2f %8.4f',
                       header=header, comments='')
            print(f"  → {result_file}")
            
            # LDEO format
            if not args.no_ldeo:
                save_ldeo_format(ctd_raw, derived, cast_id, ldeo_dir)
                print(f"  → LDEO: {ldeo_dir}/{cast_id}_ctd_*.txt")
            
            # Plots
            if not args.no_plots:
                p1 = plot_ctd_profile(binned, cast_id, plot_dir)
                if p1: print(f"  → {p1}")
            
            # Track for ODV
            all_casts.append({
                'station': cast_id,
                'lat': ctd_raw['lat'],
                'lon': ctd_raw['lon'],
                'datetime': ctd_raw.get('start_time', datetime(2026, 6, 24)),
                'bottom_depth': max_depth,
                'ctd_profile': binned,
                'ladcp_profile': {},
            })
            
        except Exception as e:
            print(f"  FAILED: {e}")
            continue
    
    # ODV output
    if all_casts and not args.no_odv:
        write_odv_collection(all_casts, odv_dir, args.cruise_id)
    
    # Summary
    write_summary(all_casts, output, args.cruise_id)
    
    print(f"\n{'='*60}")
    print(f"  Done. {len(all_casts)} cast(s) processed.")
    print(f"  Output: {output}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
