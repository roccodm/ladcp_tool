# ladcp_tool/outputs/odv_writer.py
"""Write LADCP + CTD results in ODV generic spreadsheet format.

ODV (Ocean Data View, https://odv.awi.de) accepts a single tab-separated
flat file (.txt) with station metadata repeated on every data row.
See ODV help §16.3 "Generic ODV Spreadsheet Format".
"""

import numpy as np
from pathlib import Path
from datetime import datetime


VELOCITY_QF_THRESHOLDS = {
    'good': 0.05,
    'warn': 0.10,
    'speed_questionable': 2.0,
    'speed_bad': 3.0,
}


def compute_velocity_qf(result, threshold_good=None, threshold_warn=None):
    """Assegna quality flag alle velocita' LADCP.

    Criteri basati sull'errore dell'inversione (uerr):
        QF=1: uerr <= threshold_good  (0.05 m/s default)
        QF=2: threshold_good < uerr <= threshold_warn
        QF=3: uerr > threshold_warn  (0.10 m/s default)
        QF=9: NaN

    Criteri aggiuntivi:
        QF=3: velocita' |U| o |V| > 2.0 m/s (anomalie in Mediterraneo)
        QF=4: velocita' > 3.0 m/s (certamente errate)

    Returns:
        dict con 'u_qf' e 'v_qf' arrays di int
    """
    if threshold_good is None:
        threshold_good = VELOCITY_QF_THRESHOLDS['good']
    if threshold_warn is None:
        threshold_warn = VELOCITY_QF_THRESHOLDS['warn']

    uerr = result.get('uerr', np.array([]))
    u = result.get('u', np.array([]))
    v = result.get('v', np.array([]))

    qf = np.ones(len(u), dtype=int)
    qf[np.isnan(u) | np.isnan(v)] = 9

    if len(uerr) == len(u):
        qf[(uerr > threshold_good) & (uerr <= threshold_warn)] = 2
        qf[uerr > threshold_warn] = 3

    speed = np.sqrt(u**2 + v**2)
    qf[speed > VELOCITY_QF_THRESHOLDS['speed_questionable']] = \
        np.maximum(qf[speed > VELOCITY_QF_THRESHOLDS['speed_questionable']], 3)
    qf[speed > VELOCITY_QF_THRESHOLDS['speed_bad']] = 4

    return {'u_qf': qf, 'v_qf': qf.copy()}


def _fmt(val, spec):
    """Format a float value, replacing NaN with empty string."""
    try:
        if np.isnan(val):
            return ''
    except (TypeError, ValueError):
        pass
    return f'{val:{spec}}'


def _qf(val, good=1):
    """Return QF (1=good, 9=missing) based on NaN check."""
    try:
        if np.isnan(val):
            return 9
    except (TypeError, ValueError):
        pass
    return good


def _build_cast_rows(cast, cruise_id):
    """Build all data rows (list of strings) for one cast.

    Returns list of tab-separated row strings (without trailing newline).
    """
    station = cast['station']
    lat = cast.get('lat', 0)
    lon = cast.get('lon', 0)
    dt = cast.get('datetime', datetime(2026, 6, 24))
    bdep = cast.get('bottom_depth', 0)

    ctd = cast.get('ctd_profile', {})
    ladcp = cast.get('ladcp_profile', {})

    # Build combined depth grid
    ctd_depth = ctd.get('depth', np.array([]))
    ladcp_depth = ladcp.get('depth', np.array([]))

    if len(ctd_depth) > 0:
        depth = ctd_depth
    elif len(ladcp_depth) > 0:
        depth = ladcp_depth
    else:
        return []

    # Interpolate LADCP to CTD grid if both available
    has_ladcp = len(ladcp.get('u', [])) > 0
    has_ctd = len(ctd.get('temperature', [])) > 0

    if has_ctd and has_ladcp and len(ctd_depth) > 0 and len(ladcp_depth) > 0:
        from scipy.interpolate import interp1d
        ladcp_u_interp = interp1d(ladcp_depth, ladcp['u'],
                                  kind='linear', bounds_error=False,
                                  fill_value=np.nan)(ctd_depth)
        ladcp_v_interp = interp1d(ladcp_depth, ladcp['v'],
                                  kind='linear', bounds_error=False,
                                  fill_value=np.nan)(ctd_depth)
        ladcp_err_interp = interp1d(ladcp_depth, ladcp.get('uerr',
                                    np.zeros_like(ladcp['u'])),
                                    kind='linear', bounds_error=False,
                                    fill_value=np.nan)(ctd_depth)
    else:
        ladcp_u_interp = np.full(len(depth), np.nan)
        ladcp_v_interp = np.full(len(depth), np.nan)
        ladcp_err_interp = np.full(len(depth), np.nan)

    # Get CTD data aligned to depth grid
    n = len(depth)
    T = ctd.get('temperature', np.full(n, np.nan)) if has_ctd else np.full(n, np.nan)
    S = ctd.get('salinity', np.full(n, np.nan)) if has_ctd else np.full(n, np.nan)
    sig = ctd.get('sigma0', np.full(n, np.nan)) if has_ctd else np.full(n, np.nan)
    ss = ctd.get('sound_speed', np.full(n, np.nan)) if has_ctd else np.full(n, np.nan)
    pot = ctd.get('pot_temp', np.full(n, np.nan)) if has_ctd else np.full(n, np.nan)
    P = ctd.get('pressure', np.full(n, np.nan)) if has_ctd else np.full(n, np.nan)

    # Compute quality flags
    try:
        from ladcp_tool.processors.ctd_processor import compute_ctd_qf
    except (ImportError, ModuleNotFoundError):
        from processors.ctd_processor import compute_ctd_qf
    ctd_qf = compute_ctd_qf(ctd) if has_ctd else {}
    qf_t = ctd_qf.get('temperature_qf', np.ones(n, dtype=int))
    qf_s = ctd_qf.get('salinity_qf', np.ones(n, dtype=int))
    qf_sig = ctd_qf.get('sigma0_qf', np.ones(n, dtype=int))

    vel_for_qf = {'u': ladcp_u_interp, 'v': ladcp_v_interp,
                   'uerr': ladcp_err_interp}
    vel_qf = compute_velocity_qf(vel_for_qf)
    qf_u = vel_qf['u_qf']
    qf_v = vel_qf['v_qf']

    # Format date/time for ODV generic format
    date_str = dt.strftime('%m/%d/%Y')
    time_str = dt.strftime('%H:%M')

    rows = []
    for i in range(n):
        row = (
            f"{cruise_id}\t{station}\tC\t{date_str}\t{time_str}\t"
            f"{lon:.4f}\t{lat:.4f}\t{bdep:.0f}\t"
            f"{_fmt(P[i], '.1f')}\t{_qf(P[i])}\t"
            f"{_fmt(depth[i], '.1f')}\t{_qf(depth[i])}\t"
            f"{_fmt(T[i], '.4f')}\t{qf_t[i]:d}\t"
            f"{_fmt(S[i], '.4f')}\t{qf_s[i]:d}\t"
            f"{_fmt(sig[i], '.4f')}\t{qf_sig[i]:d}\t"
            f"{_fmt(ss[i], '.1f')}\t{_qf(ss[i])}\t"
            f"{_fmt(ladcp_u_interp[i], '.4f')}\t{qf_u[i]:d}\t"
            f"{_fmt(ladcp_v_interp[i], '.4f')}\t{qf_v[i]:d}\t"
            f"{_fmt(ladcp_err_interp[i], '.4f')}\t{qf_u[i]:d}\t"
            f"{_fmt(pot[i], '.4f')}\t{_qf(pot[i])}"
        )
        rows.append(row)
    return rows


def write_odv_collection(casts_data, output_dir, cruise_id="TUNSIC26"):
    """Write all casts as a single ODV generic spreadsheet file.

    Produces ONE flat tab-separated .txt file with all stations' data
    inline. Station metadata (Cruise, Station, Type, date, time, lon,
    lat, bot. depth) is repeated on every data row, per ODV generic
    spreadsheet format (ODV help §16.3).

    The file can be imported via ODV > Import > ODV Spreadsheet,
    or drag-and-dropped onto the ODV window.

    Args:
        casts_data: list of dicts with keys: station, lat, lon, datetime,
                    bottom_depth, ctd_profile (dict), ladcp_profile (dict)
        output_dir: path to output directory
    """
    out = Path(output_dir)
    out.mkdir(exist_ok=True, parents=True)

    outfile = out / f"{cruise_id}_LADCP_ODV.txt"

    with open(outfile, 'w', encoding='utf-8') as f:
        # Optional comment lines
        f.write(f"// ODV Spreadsheet: {cruise_id} LADCP\n")
        f.write(f"// Created: {datetime.now().isoformat()}\n")
        f.write(f"// Stations: {len(casts_data)}\n")
        f.write("//\n")

        # Column header row — generic ODV format standard labels
        # Metadata: Cruise, Station, Type, mon/day/yr, hh:mm,
        #           Lon (°E), Lat (°N), Bot. Depth [m]
        # Primary var: Pressure [dbar] + QF
        # Data vars (each with QF column):
        #   Depth [m], Temperature [deg C], Salinity [PSU],
        #   SigmaTheta [kg/m3], SoundSpeed [m/s],
        #   U [m/s], V [m/s], U_Error [m/s], PotTemp [deg C]
        f.write("Cruise\tStation\tType\tmon/day/yr\thh:mm\t"
                "Lon (\u00b0E)\tLat (\u00b0N)\tBot. Depth [m]\t"
                "Pressure [dbar]\tQF\t"
                "Depth [m]\tQF\t"
                "Temperature [deg C]\tQF\t"
                "Salinity [PSU]\tQF\t"
                "SigmaTheta [kg/m3]\tQF\t"
                "SoundSpeed [m/s]\tQF\t"
                "U [m/s]\tQF\t"
                "V [m/s]\tQF\t"
                "U_Error [m/s]\tQF\t"
                "PotTemp [deg C]\tQF\n")

        # Data rows — each cast's metadata repeated on every row
        total_rows = 0
        for cast in casts_data:
            rows = _build_cast_rows(cast, cruise_id)
            for row in rows:
                f.write(row + "\n")
            total_rows += len(rows)

    print(f"  ODV spreadsheet: {outfile}  "
          f"({len(casts_data)} stations, {total_rows} rows)")
