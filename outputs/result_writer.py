# ladcp_tool/outputs/result_writer.py
"""Write processing results as text profiles and summary."""

import numpy as np
from pathlib import Path
from datetime import datetime


def write_velocity_profile(ladcp_profile, cast_id, output_dir):
    """Write LADCP velocity profile as ASCII text."""
    out = Path(output_dir) / f"{cast_id}_velocity_profile.txt"
    
    depth = ladcp_profile.get('depth', np.array([]))
    u = ladcp_profile.get('u', np.full_like(depth, np.nan))
    v = ladcp_profile.get('v', np.full_like(depth, np.nan))
    uerr = ladcp_profile.get('uerr', np.full_like(depth, np.nan))
    
    with open(out, 'w') as f:
        f.write(f"# LADCP velocity profile — Cast {cast_id}\n")
        f.write(f"# Depth(m)  U(m/s)  V(m/s)  Error(m/s)  Speed(m/s)\n")
        for i in range(len(depth)):
            speed = np.sqrt(u[i]**2 + v[i]**2) if np.isfinite(u[i]) and np.isfinite(v[i]) else np.nan
            f.write(f"{depth[i]:8.1f}  {u[i]:8.4f}  {v[i]:8.4f}  "
                    f"{uerr[i]:8.4f}  {speed:8.4f}\n")
    
    return out


def write_summary(all_results, output_dir, cruise_id="TUNSIC26"):
    """Write processing summary across all casts."""
    out = Path(output_dir) / f"{cruise_id}_LADCP_summary.txt"
    
    with open(out, 'w') as f:
        f.write(f"# {cruise_id} LADCP Processing Summary\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"#\n")
        f.write(f"# {'Cast':<10s} {'Depth(m)':>8s} {'U_min':>8s} {'U_max':>8s} "
                f"{'V_min':>8s} {'V_max':>8s} {'Error':>8s} {'Levels':>7s} {'Status':>10s}\n")
        
        for r in all_results:
            name = r.get('station', '?')
            depth_max = r.get('depth_max', 0)
            u_min = r.get('u_min', np.nan)
            u_max = r.get('u_max', np.nan)
            v_min = r.get('v_min', np.nan)
            v_max = r.get('v_max', np.nan)
            err = r.get('error_mean', np.nan)
            levels = r.get('n_levels', 0)
            status = r.get('status', 'unknown')
            
            f.write(f"  {name:<10s} {depth_max:8.1f} {u_min:8.3f} {u_max:8.3f} "
                    f"{v_min:8.3f} {v_max:8.3f} {err:8.4f} {levels:7d} {status:>10s}\n")
    
    return out
