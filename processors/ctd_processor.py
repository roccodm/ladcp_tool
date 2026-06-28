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


MEDITERRANEAN_RANGES = {
    'temperature': {'good': (-2.0, 35.0), 'warn': (-2.5, 40.0)},
    'salinity':    {'good': (2.0, 42.0),  'warn': (0.0, 45.0)},
    'sigma0':      {'good': (18.0, 30.0), 'warn': (15.0, 32.0)},
}


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


def isolate_downcast(ctd_data):
    """Estrae il solo downcast dal profilo CTD.

    Identifica il punto di massima pressione (fondo della calata) e
    trattiene solo i dati dalla superficie fino a quel punto. Applica
    poi un filtro di monotonicita per rimuovere eventuali inversioni
    residue di pressione (pause, rallentamenti non eliminati dal
    Loop Edit).

    Args:
        ctd_data: dict da extract_ctd() con chiavi 'pressure',
                  'temperature', 'conductivity', 'elapsed', ecc.

    Returns:
        ctd_data filtrato (stesso formato, meno scan).
        Aggiunge le chiavi:
            'n_scans_raw': numero scan originali
            'n_scans_downcast': numero scan nel downcast
            'p_max_index': indice dello scan di massima pressione
            'upcast_excluded': True
            'monotonicity_violations': numero scan rimossi per non-monotonicita
    """
    from scipy.ndimage import median_filter

    P = ctd_data['pressure']
    n_raw = len(P)

    if n_raw == 0:
        out = dict(ctd_data)
        out['n_scans_raw'] = 0
        out['n_scans_downcast'] = 0
        out['p_max_index'] = -1
        out['upcast_excluded'] = True
        out['monotonicity_violations'] = 0
        return out

    P_filled = P.copy()
    nan_mask = ~np.isfinite(P_filled)
    if nan_mask.any():
        idx = np.arange(n_raw)
        good = ~nan_mask
        if good.any():
            P_filled[nan_mask] = np.interp(idx[nan_mask], idx[good], P_filled[good])
        else:
            P_filled[nan_mask] = 0.0

    size = 5 if n_raw >= 5 else n_raw
    P_smooth = median_filter(P_filled, size=size)
    i_max = int(np.argmax(P_smooth))

    down_mask = np.zeros(n_raw, dtype=bool)
    down_mask[:i_max + 1] = True

    P_down = P_filled[down_mask]
    mono_mask = np.ones(len(P_down), dtype=bool)
    p_prev = P_down[0] if len(P_down) > 0 else 0.0
    n_mono_viol = 0
    for j in range(1, len(P_down)):
        if P_down[j] < p_prev:
            mono_mask[j] = False
            n_mono_viol += 1
        else:
            p_prev = P_down[j]

    down_indices = np.where(down_mask)[0]
    final_indices = down_indices[mono_mask]

    result = {}
    for key, val in ctd_data.items():
        if isinstance(val, np.ndarray) and len(val) == n_raw:
            result[key] = val[final_indices]
        else:
            result[key] = val

    result['n_scans_raw'] = n_raw
    result['n_scans_downcast'] = int(len(final_indices))
    result['p_max_index'] = i_max
    result['upcast_excluded'] = True
    result['monotonicity_violations'] = n_mono_viol

    return result


def check_pressure_monotonicity(ctd_data, fix=True):
    """Verifica e opzionalmente corregge la monotonicita della pressione.

    Usato standalone quando si mantiene l'upcast (A1 disattivo):
    rimuove gli scan con inversione di pressione rispetto al scan
    precedente. Nel downcast-only la stessa logica e integrata in
    isolate_downcast().

    Args:
        ctd_data: dict da extract_ctd()
        fix: se True, rimuove gli scan con inversione di pressione

    Returns:
        ctd_data filtrato, con chiave aggiuntiva:
            'monotonicity_violations': numero di scan rimossi
    """
    P = ctd_data['pressure']
    if len(P) == 0:
        ctd_data['monotonicity_violations'] = 0
        return ctd_data

    dP = np.diff(P)
    violations = np.where(dP < 0)[0] + 1

    if len(violations) == 0:
        ctd_data['monotonicity_violations'] = 0
        return ctd_data

    print(f"  WARNING: {len(violations)} pressure inversions detected")

    if fix:
        keep = np.ones(len(P), dtype=bool)
        keep[violations] = False
        result = {}
        for key, val in ctd_data.items():
            if isinstance(val, np.ndarray) and len(val) == len(P):
                result[key] = val[keep]
            else:
                result[key] = val
        result['monotonicity_violations'] = int(len(violations))
        return result

    ctd_data['monotonicity_violations'] = int(len(violations))
    return ctd_data


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
        if mask.sum() >= 1:
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


def bin_profile_depth(ctd_data, derived, bin_size_m=1.0):
    """Bin CTD data to uniform depth grid in meters.

    A differenza di bin_profile() che usa la pressione come asse,
    questa funzione usa la profondita' GSW come coordinata di binning.
    La profondita' e' calcolata con gsw.z_from_p() per ogni scan e il
    binning avviene direttamente su griglia metrica uniforme.

    Args:
        ctd_data: dict da extract_ctd()
        derived: dict da compute_derived() (deve contenere 'depth')
        bin_size_m: intervallo del bin in metri (default 1.0)

    Returns:
        dict analogo a bin_profile() ma con 'depth' come asse primario.
        La pressione nei bin e' la media delle pressioni degli scan
        che ricadono nel bin di profondita'.
    """
    n = len(ctd_data['pressure'])
    good = derived.get('good_mask', np.ones(n, dtype=bool))

    # derived['depth'] ha lunghezza sum(good), non len(P): crea array full-length
    depth_full = np.full(n, np.nan)
    depth_full[good] = derived['depth']

    finite = np.isfinite(depth_full) & good
    if not finite.any():
        return {k: np.array([]) for k in
                ('depth', 'pressure', 'temperature', 'salinity',
                 'sigma0', 'density', 'sound_speed', 'pot_temp')}

    d_min = np.floor(np.nanmin(depth_full[finite]))
    d_max = np.ceil(np.nanmax(depth_full[finite]))
    edges = np.arange(d_min, d_max + bin_size_m, bin_size_m)
    centers = edges[:-1] + bin_size_m / 2

    # Array full-length per derived variables (hanno lunghezza sum(good))
    sal_full = np.full(n, np.nan)
    sal_full[good] = derived.get('salinity', np.full(good.sum(), np.nan))
    sig_full = np.full(n, np.nan)
    sig_full[good] = derived.get('sigma0', np.full(good.sum(), np.nan))
    rho_full = np.full(n, np.nan)
    rho_full[good] = derived.get('density', np.full(good.sum(), np.nan))
    ss_full = np.full(n, np.nan)
    ss_full[good] = derived.get('sound_speed', np.full(good.sum(), np.nan))
    pt_full = np.full(n, np.nan)
    pt_full[good] = derived.get('pot_temp', np.full(good.sum(), np.nan))

    result = {
        'depth': centers,
        'pressure': np.full(len(centers), np.nan),
        'temperature': np.full(len(centers), np.nan),
        'salinity': np.full(len(centers), np.nan),
        'sigma0': np.full(len(centers), np.nan),
        'density': np.full(len(centers), np.nan),
        'sound_speed': np.full(len(centers), np.nan),
        'pot_temp': np.full(len(centers), np.nan),
    }

    for i in range(len(edges) - 1):
        mask = (depth_full >= edges[i]) & (depth_full < edges[i + 1]) & finite
        if mask.sum() >= 1:
            result['pressure'][i] = np.nanmean(ctd_data['pressure'][mask])
            result['temperature'][i] = np.nanmean(ctd_data['temperature'][mask])
            result['salinity'][i] = np.nanmean(sal_full[mask])
            result['sigma0'][i] = np.nanmean(sig_full[mask])
            result['density'][i] = np.nanmean(rho_full[mask])
            result['sound_speed'][i] = np.nanmean(ss_full[mask])
            result['pot_temp'][i] = np.nanmean(pt_full[mask])

    valid = np.isfinite(result['temperature'])
    for k in result:
        result[k] = result[k][valid]

    return result


def compute_ctd_qf(binned, ranges=None):
    """Assegna quality flag ODV/SeaDataNet ai dati CTD binnati.

    Criteri:
        QF=1 (good): valori nel range fisico atteso
        QF=3 (questionable): valori ai limiti del range
        QF=4 (bad): valori fuori range fisico
        QF=9 (missing): NaN

    Args:
        binned: dict da bin_profile() o bin_profile_depth()
        ranges: dict di range per variabili (default: MEDITERRANEAN_RANGES)

    Returns:
        dict con chiavi '{var}_qf', ciascuna un array di int
    """
    if ranges is None:
        ranges = MEDITERRANEAN_RANGES

    qf = {}
    for var, lim in ranges.items():
        vals = binned.get(var, np.array([]))
        flags = np.ones(len(vals), dtype=int)
        flags[np.isnan(vals)] = 9

        if len(vals) == 0:
            qf[f'{var}_qf'] = flags
            continue

        lo_warn = vals < lim['good'][0]
        hi_warn = vals > lim['good'][1]
        flags[lo_warn & (vals >= lim['warn'][0])] = 3
        flags[hi_warn & (vals <= lim['warn'][1])] = 3

        lo_bad = vals < lim['warn'][0]
        hi_bad = vals > lim['warn'][1]
        flags[lo_bad | hi_bad] = 4

        qf[f'{var}_qf'] = flags

    return qf


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
