# ladcp_tool/outputs/odv_writer.py
"""Write LADCP + CTD results in ODV-compatible spreadsheet format.

ODV (Ocean Data View, https://odv.awi.de) accepts tab-separated .txt files
with a specific header format for profile collections.
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


def write_odv_collection(casts_data, output_dir, cruise_id="TUNSIC26"):
    """Write all casts as an ODV profile collection.
    
    Args:
        casts_data: list of dicts with keys: station, lat, lon, datetime,
                    bottom_depth, ctd_profile (dict), ladcp_profile (dict)
        output_dir: path to output directory
    """
    out = Path(output_dir)
    out.mkdir(exist_ok=True, parents=True)
    
    # --- 1. Write collection metadata ---
    collection = out / f"{cruise_id}_LADCP_collection.txt"
    
    with open(collection, 'w') as f:
        f.write(f"// ODV Profile Collection: {cruise_id} LADCP\n")
        f.write(f"// Created: {datetime.now().isoformat()}\n")
        f.write("//\n")
        f.write("// <column headers>\n")
        f.write("// Cruise\tStation\tType\tyyyy-mm-ddThh:mm:ss.sss\t"
                "Longitude [degrees_east]\tLatitude [degrees_north]\t"
                "Bot. Depth [m]\n")
        
        for cast in casts_data:
            stn = cast['station']
            lat = cast.get('lat', 0)
            lon = cast.get('lon', 0)
            dt = cast.get('datetime', datetime(2026, 6, 24))
            bdep = cast.get('bottom_depth', 0)
            
            # Write line for this cruise station
            f.write(f"{cruise_id}\t{stn}\tC\t{dt.strftime('%Y-%m-%dT%H:%M:%S')}\t"
                    f"{lon:.4f}\t{lat:.4f}\t{bdep:.0f}\n")
    
    print(f"  ODV collection: {collection}")
    
    # --- 2. Write per-cast data files ---
    for cast in casts_data:
        write_cast_odv(cast, out, cruise_id)


def write_cast_odv(cast, output_dir, cruise_id="TUNSIC26"):
    """Write a single cast in ODV spreadsheet format.
    
    Creates a tab-separated file with:
      - Cruise metadata header
      - Per-depth data: Pressure, Depth, Temperature, Salinity, Sigma0,
        SoundSpeed, U, V, U_error, PotTemp
    """
    station = cast['station']
    lat = cast.get('lat', 0)
    lon = cast.get('lon', 0)
    dt = cast.get('datetime', datetime(2026, 6, 24))
    bdep = cast.get('bottom_depth', 0)
    
    ctd = cast.get('ctd_profile', {})
    ladcp = cast.get('ladcp_profile', {})
    
    outfile = Path(output_dir) / f"{cruise_id}_{station}_LADCP.txt"
    
    with open(outfile, 'w') as f:
        # Header
        f.write(f"// ODV Spreadsheet: {cruise_id} Station {station}\n")
        f.write("//\n")
        f.write("Cruise\tStation\tType\t" 
                "yyyy-mm-ddThh:mm:ss.sss\t"
                "Longitude [degrees_east]\tLatitude [degrees_north]\t"
                "Bot. Depth [m]\n")
        f.write(f"{cruise_id}\t{station}\tC\t"
                f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}\t"
                f"{lon:.4f}\t{lat:.4f}\t{bdep:.0f}\n")
        f.write("//\n")
        
        # Variable metadata
        f.write("// <Variable name=\"Pressure [dbar]\" unit=\"dbar\">\n")
        f.write("// <Variable name=\"Depth [m]\" unit=\"m\">\n")
        f.write("// <Variable name=\"Temperature [deg C]\" unit=\"degC\">\n")
        f.write("// <Variable name=\"QF:Temperature\">\n")
        f.write("// <Variable name=\"Salinity [PSU]\" unit=\"PSU\">\n")
        f.write("// <Variable name=\"QF:Salinity\">\n")
        f.write("// <Variable name=\"SigmaTheta [kg/m3]\" unit=\"kg/m3\">\n")
        f.write("// <Variable name=\"QF:SigmaTheta\">\n")
        f.write("// <Variable name=\"SoundSpeed [m/s]\" unit=\"m/s\">\n")
        f.write("// <Variable name=\"U [m/s]\" unit=\"m/s\">\n")
        f.write("// <Variable name=\"QF:U\">\n")
        f.write("// <Variable name=\"V [m/s]\" unit=\"m/s\">\n")
        f.write("// <Variable name=\"QF:V\">\n")
        f.write("// <Variable name=\"U_Error [m/s]\" unit=\"m/s\">\n")
        f.write("// <Variable name=\"PotTemp [deg C]\" unit=\"degC\">\n")
        f.write("//\n")

        # Column headers
        f.write("Pressure [dbar]\tDepth [m]\tTemperature [deg C]\t"
                "QF:Temperature\tSalinity [PSU]\tQF:Salinity\t"
                "SigmaTheta [kg/m3]\tQF:SigmaTheta\tSoundSpeed [m/s]\t"
                "U [m/s]\tQF:U\tV [m/s]\tQF:V\tU_Error [m/s]\tPotTemp [deg C]\n")
        
        # Build combined depth grid
        ctd_depth = ctd.get('depth', np.array([]))
        ladcp_depth = ladcp.get('depth', np.array([]))
        
        if len(ctd_depth) > 0:
            depth = ctd_depth
        elif len(ladcp_depth) > 0:
            depth = ladcp_depth
        else:
            return
        
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
        T = ctd.get('temperature', np.full(len(depth), np.nan)) if has_ctd else np.full(len(depth), np.nan)
        S = ctd.get('salinity', np.full(len(depth), np.nan)) if has_ctd else np.full(len(depth), np.nan)
        sig = ctd.get('sigma0', np.full(len(depth), np.nan)) if has_ctd else np.full(len(depth), np.nan)
        ss = ctd.get('sound_speed', np.full(len(depth), np.nan)) if has_ctd else np.full(len(depth), np.nan)
        pot = ctd.get('pot_temp', np.full(len(depth), np.nan)) if has_ctd else np.full(len(depth), np.nan)
        P = ctd.get('pressure', np.full(len(depth), np.nan)) if has_ctd else np.full(len(depth), np.nan)

        # Compute quality flags
        from ladcp_tool.processors.ctd_processor import compute_ctd_qf
        ctd_qf = compute_ctd_qf(ctd) if has_ctd else {}
        qf_t = ctd_qf.get('temperature_qf', np.ones(len(depth), dtype=int))
        qf_s = ctd_qf.get('salinity_qf', np.ones(len(depth), dtype=int))
        qf_sig = ctd_qf.get('sigma0_qf', np.ones(len(depth), dtype=int))

        vel_for_qf = {'u': ladcp_u_interp, 'v': ladcp_v_interp,
                       'uerr': ladcp_err_interp}
        vel_qf = compute_velocity_qf(vel_for_qf)
        qf_u = vel_qf['u_qf']
        qf_v = vel_qf['v_qf']

        # Write data rows
        for i in range(len(depth)):
            f.write(f"{P[i]:.1f}\t{depth[i]:.1f}\t{T[i]:.4f}\t{qf_t[i]:d}\t"
                    f"{S[i]:.4f}\t{qf_s[i]:d}\t"
                    f"{sig[i]:.4f}\t{qf_sig[i]:d}\t{ss[i]:.1f}\t"
                    f"{ladcp_u_interp[i]:.4f}\t{qf_u[i]:d}\t"
                    f"{ladcp_v_interp[i]:.4f}\t{qf_v[i]:d}\t"
                    f"{ladcp_err_interp[i]:.4f}\t{pot[i]:.4f}\n")
    
    print(f"  ODV file: {outfile}")
