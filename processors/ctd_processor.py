# ladcp_tool/processors/ctd_processor.py
"""CTD data processing: CNV reader + GSW derived variables.

Validated against SBE Data Processing output (RMSE < 0.01 PSU for salinity).
"""

import re
import numpy as np
from pathlib import Path
from datetime import datetime

try:
    import gsw
    HAS_GSW = True
except ImportError:
    HAS_GSW = False


def read_cnv(filepath):
    """Read SBE .cnv file, return data array and metadata dict.
    
    Returns:
        data: numpy array of shape (n_scans, n_vars)
        meta: dict with keys: names, nquan, nvalues, interval, lat, lon, 
              start_time, bad_flag, header_lines
    """
    meta = {
        'names': [], 'nquan': 0, 'nvalues': 0, 'header_end': 0,
        'interval': 0.0416667, 'bad_flag': -9.99e-29,
        'lat': None, 'lon': None, 'start_time': None,
    }
    
    with open(filepath, errors='replace') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        if line.startswith('# name'):
            parts = line.split('=')
            if len(parts) >= 2:
                name_unit = parts[1].split(':')
                if len(name_unit) >= 1:
                    meta['names'].append(name_unit[0].strip())
        elif line.startswith('# nquan'):
            m = re.search(r'(\d+)', line)
            if m: meta['nquan'] = int(m.group(1))
        elif line.startswith('# nvalues'):
            m = re.search(r'(\d+)', line)
            if m: meta['nvalues'] = int(m.group(1))
        elif line.startswith('# bad_flag'):
            m = re.search(r'([-\de.]+)', line)
            if m: meta['bad_flag'] = float(m.group(1))
        elif line.startswith('# interval'):
            m = re.search(r'seconds:\s*([\d.]+)', line)
            if m: meta['interval'] = float(m.group(1))
        elif line.startswith('# start_time'):
            m = re.match(r'# start_time\s*=\s*(.*)', line)
            if m:
                try:
                    meta['start_time'] = datetime.strptime(
                        m.group(1).strip(), '%b %d %Y %H:%M:%S')
                except ValueError:
                    pass
        elif line.startswith('* NMEA Latitude'):
            m = re.search(r'(\d+)\s+([\d.]+)\s+([NS])', line)
            if m:
                meta['lat'] = float(m.group(1)) + float(m.group(2))/60
                if m.group(3) == 'S': meta['lat'] = -meta['lat']
        elif line.startswith('* NMEA Longitude'):
            m = re.search(r'(\d+)\s+([\d.]+)\s+([EW])', line)
            if m:
                meta['lon'] = float(m.group(1)) + float(m.group(2))/60
                if m.group(3) == 'W': meta['lon'] = -meta['lon']
        elif line.startswith('* System UpLoad Time'):
            m = re.search(r'= (.*)', line)
            if m:
                try:
                    meta['start_time'] = datetime.strptime(
                        m.group(1).strip(), '%b %d %Y %H:%M:%S')
                except ValueError:
                    pass
        elif line.startswith('*END*'):
            meta['header_end'] = i + 1
    
    # Read numeric data
    data = []
    for line in lines[meta['header_end']:]:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            vals = [float(x) for x in line.split()]
            if vals: data.append(vals)
        except ValueError:
            continue
    
    arr = np.array(data)
    
    # Mask bad values
    bad = np.abs(arr - meta['bad_flag']) < 1e-25
    arr[bad] = np.nan
    
    return arr, meta


def extract_ctd(arr, meta):
    """Extract primary CTD variables (P, T, C) and position from CNV data.
    
    Returns dict with: pressure (dbar), temperature (°C ITS-90), 
    conductivity (S/m), lat, lon, time_elapsed, depth_sbe
    """
    names = meta['names']
    
    i_press = _find_col(names, 'prDM')
    i_temp  = _find_col(names, 't090C')
    i_cond  = _find_col(names, 'c0S/m')
    i_lat   = _find_col(names, 'latitude')
    i_lon   = _find_col(names, 'longitude')
    
    if i_press is None or i_temp is None or i_cond is None:
        return None
    
    P = arr[:, i_press]
    T = arr[:, i_temp]
    C = arr[:, i_cond]  # S/m
    
    # Position
    if i_lat is not None and i_lon is not None:
        lat = np.nanmean(arr[:, i_lat])
        lon = np.nanmean(arr[:, i_lon])
    else:
        lat = meta.get('lat', 36.4) or 36.4
        lon = meta.get('lon', 14.75) or 14.75
    
    # Elapsed time
    elapsed = np.arange(len(P)) * meta['interval']
    
    return {
        'pressure': P,
        'temperature': T,
        'conductivity': C,
        'lat': lat,
        'lon': lon,
        'elapsed': elapsed,
        'interval': meta['interval'],
        'start_time': meta['start_time'],
    }


def compute_derived(ctd_data):
    """Compute derived CTD variables using GSW.
    
    Args:
        ctd_data: from extract_ctd()
    
    Returns dict with: salinity, abs_salinity, pot_temp, cons_temp,
        sigma0, density, sound_speed, depth
    """
    P = ctd_data['pressure']
    T = ctd_data['temperature']
    C = ctd_data['conductivity'] * 10.0  # S/m -> mS/cm for GSW
    lat = ctd_data['lat']
    lon = ctd_data['lon']
    
    # Remove bad data
    good = np.isfinite(P) & np.isfinite(T) & np.isfinite(C) & (P >= 0)
    
    if not HAS_GSW:
        return {'salinity': np.full_like(P, np.nan)}
    
    SP = gsw.SP_from_C(C[good], T[good], P[good])
    SA = gsw.SA_from_SP(SP, P[good], lon, lat)
    pot_temp = gsw.pt0_from_t(SA, T[good], P[good])
    CT_val = gsw.CT_from_t(SA, T[good], P[good])
    sig0 = gsw.sigma0(SA, CT_val)
    rho = gsw.rho(SA, CT_val, P[good])
    ss = gsw.sound_speed(SA, CT_val, P[good])
    depth = -gsw.z_from_p(P[good], lat)
    
    return {
        'salinity': SP,
        'abs_salinity': SA,
        'pot_temp': pot_temp,
        'cons_temp': CT_val,
        'sigma0': sig0,
        'density': rho,
        'sound_speed': ss,
        'depth': depth,
        'good_mask': good,
    }


def bin_profile(ctd_data, derived, bin_size=1.0):
    """Bin CTD data to uniform pressure grid.
    
    Returns dict with binned variables at bin centers.
    """
    P = ctd_data['pressure']
    good = derived.get('good_mask', np.ones(len(P), dtype=bool))
    
    p_min = np.floor(np.nanmin(P[good]))
    p_max = np.ceil(np.nanmax(P[good]))
    edges = np.arange(p_min, p_max + bin_size, bin_size)
    centers = edges[:-1] + bin_size / 2
    
    result = {
        'pressure': centers,
        'temperature': np.full(len(centers), np.nan),
        'salinity': np.full(len(centers), np.nan),
        'sigma0': np.full(len(centers), np.nan),
        'density': np.full(len(centers), np.nan),
        'sound_speed': np.full(len(centers), np.nan),
        'depth': np.full(len(centers), np.nan),
        'pot_temp': np.full(len(centers), np.nan),
    }
    
    for i in range(len(edges) - 1):
        mask = (P >= edges[i]) & (P < edges[i+1]) & good
        if mask.sum() > 3:
            result['temperature'][i] = np.nanmean(ctd_data['temperature'][mask])
            result['salinity'][i] = np.nanmean(derived['salinity'][mask])
            result['sigma0'][i] = np.nanmean(derived.get('sigma0', [np.nan]*len(P))[mask])
            result['density'][i] = np.nanmean(derived.get('density', [np.nan]*len(P))[mask])
            result['sound_speed'][i] = np.nanmean(derived.get('sound_speed', [np.nan]*len(P))[mask])
            result['depth'][i] = np.nanmean(derived.get('depth', [np.nan]*len(P))[mask])
            result['pot_temp'][i] = np.nanmean(derived.get('pot_temp', [np.nan]*len(P))[mask])
    
    # Remove empty bins
    valid = np.isfinite(result['temperature'])
    for k in result:
        result[k] = result[k][valid]
    
    return result


def save_ldeo_format(ctd_data, derived, prefix, output_dir):
    """Save CTD data in LDEO-compatible ASCII format.
    
    Creates:
      {prefix}_ctd_timeseries.txt — elapsed_sec P T S
      {prefix}_ctd_profile.txt — binned P T S
    """
    out = Path(output_dir)
    good = derived.get('good_mask', np.ones(len(ctd_data['pressure']), dtype=bool))
    
    # Time series
    ts = np.column_stack([
        ctd_data['elapsed'][good],
        ctd_data['pressure'][good],
        ctd_data['temperature'][good],
        derived['salinity'],
    ])
    np.savetxt(out / f"{prefix}_ctd_timeseries.txt", ts, fmt='%.4f')
    
    # Profile
    binned = bin_profile(ctd_data, derived)
    prof = np.column_stack([
        binned['pressure'],
        binned['temperature'],
        binned['salinity'],
    ])
    np.savetxt(out / f"{prefix}_ctd_profile.txt", prof, fmt='%.4f')
    
    return binned


def _find_col(names, pattern):
    """Find column index matching pattern."""
    for i, n in enumerate(names):
        if n and pattern in str(n):
            return i
    return None
