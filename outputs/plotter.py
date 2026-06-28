# ladcp_tool/outputs/plotter.py
"""Generate profile plots from LADCP processing results."""

import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot_velocity_profile(ladcp_profile, cast_id, output_dir, dpi=120):
    """Plot U, V velocity profile with error bars."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 10), sharey=True)
    
    depth = ladcp_profile.get('depth', np.array([]))
    u = ladcp_profile.get('u', np.array([]))
    v = ladcp_profile.get('v', np.array([]))
    uerr = ladcp_profile.get('uerr', np.array([]))
    
    if len(depth) == 0:
        plt.close()
        return
    
    # U component
    ax = axes[0]
    ax.plot(u, depth, 'b.-', lw=1.5, ms=4)
    if len(uerr) > 0:
        ax.fill_betweenx(depth, u - uerr, u + uerr, alpha=0.2, color='b')
    ax.axvline(0, color='k', ls='--', alpha=0.3)
    ax.set_xlabel('U (East) [m/s]')
    ax.set_ylabel('Depth [m]')
    ax.invert_yaxis()
    ax.set_title(f'{cast_id} — East Velocity')
    ax.grid(alpha=0.3)
    
    # V component
    ax = axes[1]
    ax.plot(v, depth, 'r.-', lw=1.5, ms=4)
    if len(uerr) > 0:
        ax.fill_betweenx(depth, v - uerr, v + uerr, alpha=0.2, color='r')
    ax.axvline(0, color='k', ls='--', alpha=0.3)
    ax.set_xlabel('V (North) [m/s]')
    ax.set_title(f'{cast_id} — North Velocity')
    ax.grid(alpha=0.3)
    
    # Speed
    ax = axes[2]
    speed = np.sqrt(u**2 + v**2)
    ax.plot(speed, depth, 'k.-', lw=1.5, ms=4)
    ax.set_xlabel('Speed [m/s]')
    ax.set_title(f'{cast_id} — Horizontal Speed')
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    outfile = Path(output_dir) / f"{cast_id}_velocity.png"
    plt.savefig(outfile, dpi=dpi, bbox_inches='tight')
    plt.close()
    return outfile


def plot_ctd_profile(ctd_profile, cast_id, output_dir, dpi=120):
    """Plot T-S diagram and CTD profiles."""
    if len(ctd_profile.get('depth', [])) == 0:
        return
    
    depth = ctd_profile['depth']
    T = ctd_profile.get('temperature', np.full(len(depth), np.nan))
    S = ctd_profile.get('salinity', np.full(len(depth), np.nan))
    sig0 = ctd_profile.get('sigma0', np.full(len(depth), np.nan))
    ss = ctd_profile.get('sound_speed', np.full(len(depth), np.nan))
    pot = ctd_profile.get('pot_temp', np.full(len(depth), np.nan))
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 10))
    
    # T-S diagram
    ax = axes[0]
    sc = ax.scatter(S, pot, c=depth, s=8, alpha=0.7, cmap='viridis')
    ax.set_xlabel('Salinity [PSU]')
    ax.set_ylabel('Potential Temperature [°C]')
    ax.set_title(f'{cast_id} — T-S Diagram')
    plt.colorbar(sc, ax=ax, label='Depth [m]')
    ax.grid(alpha=0.3)
    
    # T, S vs depth
    ax = axes[1]
    ax.plot(T, depth, 'r-', lw=1.5, label='Temperature')
    ax_twin = ax.twiny()
    ax_twin.plot(S, depth, 'b-', lw=1.5, label='Salinity')
    ax.set_xlabel('Temperature [°C]', color='r')
    ax_twin.set_xlabel('Salinity [PSU]', color='b')
    ax.set_ylabel('Depth [m]')
    ax.invert_yaxis()
    ax.set_title(f'{cast_id} — Vertical Profiles')
    ax.grid(alpha=0.3)
    
    # Sigma0 and sound speed
    ax = axes[2]
    ax.plot(sig0, depth, 'g-', lw=1.5, label='σ₀')
    ax_twin2 = ax.twiny()
    ax_twin2.plot(ss, depth, 'orange', lw=1.5, label='Sound Speed')
    ax.set_xlabel('σ₀ [kg/m³]', color='g')
    ax_twin2.set_xlabel('Sound Speed [m/s]', color='orange')
    ax.set_ylabel('Depth [m]')
    ax.invert_yaxis()
    ax.set_title(f'{cast_id} — Density & Sound Speed')
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    outfile = Path(output_dir) / f"{cast_id}_ctd.png"
    plt.savefig(outfile, dpi=dpi, bbox_inches='tight')
    plt.close()
    return outfile


def plot_combined(ctd_profile, ladcp_profile, cast_id, output_dir, dpi=120):
    """Combined plot: velocity + CTD on one figure."""
    ctd_depth = ctd_profile.get('depth', np.array([]))
    ladcp_depth = ladcp_profile.get('depth', np.array([]))
    
    if len(ctd_depth) == 0 and len(ladcp_depth) == 0:
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    
    # Use CTD depth grid if available
    depth = ctd_depth if len(ctd_depth) > 0 else ladcp_depth
    
    # Velocity
    ax = axes[0, 0]
    u = ladcp_profile.get('u', np.full(len(depth), np.nan))
    v = ladcp_profile.get('v', np.full(len(depth), np.nan))
    if len(ladcp_depth) > 0 and len(ctd_depth) > 0 and len(ladcp_depth) != len(ctd_depth):
        from scipy.interpolate import interp1d
        u = interp1d(ladcp_depth, u, kind='linear', 
                     bounds_error=False, fill_value=np.nan)(ctd_depth)
        v = interp1d(ladcp_depth, v, kind='linear',
                     bounds_error=False, fill_value=np.nan)(ctd_depth)
    
    ax.plot(u, depth, 'b-', lw=1.5, label='U (East)')
    ax.plot(v, depth, 'r-', lw=1.5, label='V (North)')
    ax.axvline(0, color='k', ls='--', alpha=0.3)
    ax.set_xlabel('Velocity [m/s]')
    ax.set_ylabel('Depth [m]')
    ax.invert_yaxis()
    ax.legend()
    ax.set_title(f'{cast_id} — LADCP Velocity')
    ax.grid(alpha=0.3)
    
    # T-S
    ax = axes[0, 1]
    T = ctd_profile.get('temperature', np.full(len(depth), np.nan))
    S = ctd_profile.get('salinity', np.full(len(depth), np.nan))
    pot = ctd_profile.get('pot_temp', np.full(len(depth), np.nan))
    sc = ax.scatter(S, pot, c=depth, s=6, alpha=0.7, cmap='viridis')
    ax.set_xlabel('Salinity [PSU]')
    ax.set_ylabel('Pot. Temp. [°C]')
    ax.set_title(f'{cast_id} — T-S')
    plt.colorbar(sc, ax=ax, label='m')
    ax.grid(alpha=0.3)
    
    # T + S profiles
    ax = axes[1, 0]
    ax.plot(T, depth, 'r-', lw=1.5)
    ax_twin = ax.twiny()
    ax_twin.plot(S, depth, 'b-', lw=1.5)
    ax.set_xlabel('Temp [°C]', color='r')
    ax_twin.set_xlabel('Sal [PSU]', color='b')
    ax.set_ylabel('Depth [m]')
    ax.invert_yaxis()
    ax.set_title(f'{cast_id} — T & S')
    ax.grid(alpha=0.3)
    
    # Density
    ax = axes[1, 1]
    sig0 = ctd_profile.get('sigma0', np.full(len(depth), np.nan))
    ss = ctd_profile.get('sound_speed', np.full(len(depth), np.nan))
    ax.plot(sig0, depth, 'g-', lw=1.5)
    ax_twin2 = ax.twiny()
    ax_twin2.plot(ss, depth, 'orange', lw=1.5)
    ax.set_xlabel('σ₀ [kg/m³]', color='g')
    ax_twin2.set_xlabel('Sound Speed [m/s]', color='orange')
    ax.set_ylabel('Depth [m]')
    ax.invert_yaxis()
    ax.set_title(f'{cast_id} — Density & SS')
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    outfile = Path(output_dir) / f"{cast_id}_combined.png"
    plt.savefig(outfile, dpi=dpi, bbox_inches='tight')
    plt.close()
    return outfile
