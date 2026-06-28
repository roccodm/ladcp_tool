#!/usr/bin/env python3
"""
ladcp_tool — Process LADCP .000 files with LDEO IX (Octave).

Reads RDI Workhorse binary files, matches with CTD data if available,
runs LDEO IX processing via GNU Octave, and outputs velocity profiles,
plots, and ODV-compatible spreadsheets.

Usage:
    ladcp_tool --source-dir ./00-LADCP-raw --output-dir ./ladcp_out
    ladcp_tool -s ./00-LADCP-raw --ctd-dir ./02-CTD-processed -o ./ladcp_out
    ladcp_tool -s ./00-LADCP-raw -o ./ladcp_out --skip-octave
"""

import sys
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ladcp_tool.utils.cast_matcher import find_ladcp_files, find_ctd_files, match_casts
from ladcp_tool.processors.rdi_reader import RDIFile
from ladcp_tool.processors.ctd_processor import (
    read_cnv, extract_ctd, compute_derived, bin_profile, save_ldeo_format,
)
from ladcp_tool.processors.ldeo_runner import (
    create_set_cast_params, run_octave_processing, read_ldeo_result,
    LDEO_PATCHED, LDEO_GEOMAG,
)
from ladcp_tool.outputs.odv_writer import write_odv_collection
from ladcp_tool.outputs.plotter import plot_velocity_profile, plot_ctd_profile, plot_combined
from ladcp_tool.outputs.result_writer import write_velocity_profile, write_summary


def main():
    parser = argparse.ArgumentParser(
        description="ladcp_tool — Process LADCP .000 files with LDEO IX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ladcp_tool -s ./00-LADCP-raw -o ./ladcp_out
  ladcp_tool -s ./00-LADCP-raw --ctd-dir ./02-CTD-processed -o ./ladcp_out
  ladcp_tool -s ./00-LADCP-raw -o ./ladcp_out --skip-octave --quick-look
""")
    
    parser.add_argument('-s', '--source-dir', required=True,
                        help='Directory with MASTE*.000 / SLAVE*.000 files')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for results, plots, ODV files')
    parser.add_argument('--ctd-dir', default=None,
                        help='Directory with .cnv CTD files (optional, enables full LDEO)')
    parser.add_argument('--xmlcon', default=None,
                        help='SBE XMLCON file for CTD configuration')
    parser.add_argument('--skip-octave', action='store_true',
                        help='Skip Octave processing (do only quick-look from Python)')
    parser.add_argument('--quick-look', action='store_true',
                        help='Generate quick-look plots from raw LADCP data only')
    parser.add_argument('--timeout', type=int, default=600,
                        help='Timeout per cast for Octave (seconds, default: 600)')
    parser.add_argument('--cruise-id', default='TUNSIC26',
                        help='Cruise identifier (default: TUNSIC26)')
    parser.add_argument('--no-plots', action='store_true',
                        help='Skip plot generation')
    parser.add_argument('--no-odv', action='store_true',
                        help='Skip ODV file generation')
    
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
    work_dir = output / "work"
    ctd_ascii_dir = output / "ctd_ascii"
    
    for d in [res_dir, plot_dir, odv_dir, work_dir, ctd_ascii_dir]:
        d.mkdir(exist_ok=True, parents=True)
    
    print(f"{'='*60}")
    print(f"  ladcp_tool — LADCP Processing with LDEO IX")
    print(f"  LADCP source: {source}")
    if args.ctd_dir:
        print(f"  CTD source:   {args.ctd_dir}")
    print(f"  Output:       {output}")
    print(f"  Octave:       {'disabled' if args.skip_octave else 'enabled'}")
    print(f"{'='*60}\n")
    
    # --- Find and match files ---
    ladcp_casts = find_ladcp_files(source)
    print(f"Found {len(ladcp_casts)} LADCP cast(s): {sorted(ladcp_casts.keys())}")
    
    ctd_files = {}
    if args.ctd_dir:
        ctd_files = find_ctd_files(args.ctd_dir)
        print(f"Found {len(ctd_files)} CTD file(s)")
    
    xmlcon = args.xmlcon
    if xmlcon is None and args.ctd_dir:
        # Try to find XMLCON
        parent = Path(args.ctd_dir).parent
        for cand in parent.glob("**/*.xmlcon"):
            xmlcon = str(cand)
            break
        if xmlcon is None:
            for cand in Path(args.ctd_dir).parent.parent.glob("**/*.xmlcon"):
                xmlcon = str(cand)
                break
    
    matches, unmatched_l, unmatched_c = match_casts(ladcp_casts, ctd_files, xmlcon)
    
    if unmatched_l:
        print(f"LADCP without CTD: {unmatched_l}")
    if unmatched_c:
        print(f"CTD without LADCP: {unmatched_c}")
    
    print(f"\nProcessing {len(matches)} cast(s) with matched CTD\n")
    
    all_results = []
    
    for cast in matches:
        station = cast['station']
        print(f"{'─'*50}")
        print(f"Cast {station}")
        print(f"  LADCP down: {Path(cast['down_file']).name if cast['down_file'] else '—'}")
        print(f"  LADCP up:   {Path(cast['up_file']).name if cast['up_file'] else '—'}")
        print(f"  CTD:        {Path(cast['ctd_file']).name if cast.get('ctd_file') else '—'}")
        
        result = {
            'station': station,
            'status': 'pending',
            'lat': 36.4, 'lon': 14.75,
        }
        
        # --- Process CTD if available ---
        binned_ctd = {}
        if cast.get('ctd_file'):
            try:
                arr, meta = read_cnv(cast['ctd_file'])
                ctd_raw = extract_ctd(arr, meta)
                if ctd_raw:
                    derived = compute_derived(ctd_raw)
                    binned_ctd = bin_profile(ctd_raw, derived)
                    
                    # Save LDEO-compatible CTD ASCII
                    save_ldeo_format(ctd_raw, derived, station, ctd_ascii_dir)
                    cast['ctd_timeseries'] = str(ctd_ascii_dir / f"{station}_ctd_timeseries.txt")
                    cast['ctd_profile'] = str(ctd_ascii_dir / f"{station}_ctd_profile.txt")
                    
                    result['lat'] = ctd_raw['lat']
                    result['lon'] = ctd_raw['lon']
                    result['datetime'] = ctd_raw.get('start_time')
                    result['bottom_depth'] = np.nanmax(binned_ctd.get('depth', [0]))
                    
                    print(f"  CTD: {len(binned_ctd['depth'])} levels, "
                          f"max {result['bottom_depth']:.0f} m")
            except Exception as e:
                print(f"  CTD processing failed: {e}")
        
        # --- Quick-Look (always do if no Octave) ---
        if args.quick_look or args.skip_octave:
            try:
                ladcp_data = _read_ladcp_quicklook(cast, work_dir)
                if ladcp_data:
                    result['n_ensembles'] = ladcp_data.get('n_ensembles', 0)
                    result['depth_max'] = ladcp_data.get('max_depth', 0)
                    print(f"  Quick-look: {result['n_ensembles']} ensembles, "
                          f"depth {result['depth_max']:.0f} m")
            except Exception as e:
                print(f"  Quick-look failed: {e}")
        
        # --- Octave LDEO processing ---
        if not args.skip_octave:
            if not Path(LDEO_PATCHED).exists():
                print(f"  WARNING: LDEO patched code not found at {LDEO_PATCHED}")
                print(f"  Set LDEO_PATCHED in ldeo_runner.py or install TUNSIC26 package")
            else:
                try:
                    create_set_cast_params(cast, work_dir, f"result_{station}")
                    success, msg = run_octave_processing(cast, work_dir, args.timeout)
                    
                    if success:
                        result_file = work_dir / f"result_{station}_profile.txt"
                        if result_file.exists():
                            ldeo = read_ldeo_result(result_file)
                            
                            # Copy to results dir
                            result['ladcp_profile'] = ldeo
                            result['status'] = 'success'
                            result['depth_max'] = np.nanmax(ldeo['depth'])
                            result['u_min'] = np.nanmin(ldeo['u'])
                            result['u_max'] = np.nanmax(ldeo['u'])
                            result['v_min'] = np.nanmin(ldeo['v'])
                            result['v_max'] = np.nanmax(ldeo['v'])
                            result['error_mean'] = np.nanmean(ldeo['uerr'])
                            result['n_levels'] = len(ldeo['depth'])
                            
                            write_velocity_profile(ldeo, station, res_dir)
                            print(f"  LDEO: SUCCESS — {result['n_levels']} levels, "
                                  f"err={result['error_mean']:.4f} m/s")
                            
                            # Plots
                            if not args.no_plots:
                                plot_velocity_profile(ldeo, station, plot_dir)
                                if binned_ctd:
                                    plot_combined(binned_ctd, ldeo, station, plot_dir)
                                    print(f"  → {plot_dir}/{station}_*.png")
                        else:
                            result['status'] = 'partial'
                            print(f"  LDEO: ran but no output file")
                    else:
                        result['status'] = 'octave_failed'
                        print(f"  LDEO: FAILED — {msg[:200]}")
                except Exception as e:
                    result['status'] = 'error'
                    print(f"  LDEO error: {e}")
        else:
            if binned_ctd:
                result['status'] = 'ctd_only'
            else:
                result['status'] = 'no_processing'
        
        all_results.append(result)
    
    # --- ODV output ---
    if all_results and not args.no_odv:
        odv_casts = []
        for r in all_results:
            odv_casts.append({
                'station': r['station'],
                'lat': r.get('lat', 0),
                'lon': r.get('lon', 0),
                'datetime': r.get('datetime', datetime(2026, 6, 24)),
                'bottom_depth': r.get('bottom_depth', r.get('depth_max', 0)),
                'ctd_profile': r.get('ctd_profile', binned_ctd),
                'ladcp_profile': r.get('ladcp_profile', {}),
            })
        write_odv_collection(odv_casts, odv_dir, args.cruise_id)
    
    # --- Summary ---
    write_summary(all_results, output, args.cruise_id)
    
    # Show summary
    ok = sum(1 for r in all_results if r['status'] == 'success')
    fail = sum(1 for r in all_results if r['status'] != 'success')
    print(f"\n{'='*60}")
    print(f"  Done. {ok} success, {fail} non-critical, {len(all_results)} total")
    print(f"  Output: {output}")
    print(f"{'='*60}")


def _read_ladcp_quicklook(cast, work_dir):
    """Quick-look read of LADCP data without full processing."""
    down = cast.get('down_file')
    up = cast.get('up_file')
    
    if not down:
        return None
    
    rdi = RDIFile(down)
    n = len(rdi)
    if n == 0:
        return None
    
    depths = []
    for ens in rdi:
        d = ens.get('depth_xdcr', 0)
        if np.isfinite(d):
            depths.append(d)
    
    max_depth = max(depths) if depths else 0
    
    return {
        'n_ensembles': n,
        'max_depth': max_depth,
        'file': Path(down).name,
    }


if __name__ == '__main__':
    main()
