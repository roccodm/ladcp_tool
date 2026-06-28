# ladcp_tool/utils/cast_matcher.py
"""Match LADCP and CTD files by station ID."""

import re
from pathlib import Path


def find_ladcp_files(source_dir):
    """Find all LADCP .000 files, return {station_id: (down_path, up_path)}."""
    source = Path(source_dir)
    casts = {}
    
    for f in sorted(source.glob("*.000")):
        name = f.stem  # e.g. "MASTE299" or "SLAVET840"
        
        # Parse instrument and station
        if name.startswith("MASTE"):
            station = name[5:]  # after MASTE
            inst = "down"
        elif name.startswith("SLAVE"):
            station = name[5:]  # after SLAVE
            inst = "up"
        else:
            continue
        
        if station not in casts:
            casts[station] = {"down": None, "up": None}
        casts[station][inst] = str(f)
    
    return casts


def find_ctd_files(source_dir):
    """Find CTD .cnv files, return {station_id: cnv_path}.
    
    Matches station numbers with optional S/T prefix and 'bis' suffix.
    Also handles TUNSIC naming convention (e.g. S299TUNSIC → S299).
    """
    source = Path(source_dir)
    cnv_files = {}
    
    for f in sorted(source.glob("*.cnv")):
        name = f.stem
        
        # Remove common suffixes
        for suffix in ["TUNSIC", "_processed", "_cnv"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        
        # Handle station IDs
        station = name
        cnv_files[station] = str(f)
    
    return cnv_files


def match_casts(ladcp_casts, ctd_files, xmlcon_path=None):
    """Match LADCP and CTD casts by station ID.
    
    Returns list of dicts with keys: station, down_file, up_file, ctd_file
    """
    matched = []
    unmatched_ladcp = []
    unmatched_ctd = set(ctd_files.keys())
    
    for station, ladcp in ladcp_casts.items():
        ctd_path = None
        
        # Direct match
        if station in ctd_files:
            ctd_path = ctd_files[station]
        # Try with S prefix
        elif f"S{station}" in ctd_files:
            ctd_path = ctd_files[f"S{station}"]
        # Try with T prefix  
        elif f"T{station}" in ctd_files:
            ctd_path = ctd_files[f"T{station}"]
        # Try without prefix (S299 -> 299)
        elif station.startswith("S") and station[1:] in ctd_files:
            ctd_path = ctd_files[station[1:]]
        elif station.startswith("T") and station[1:] in ctd_files:
            ctd_path = ctd_files[station[1:]]
        # Try 'bis' suffix
        elif f"{station}bis" in ctd_files:
            ctd_path = ctd_files[f"{station}bis"]
        
        if ctd_path:
            matched.append({
                "station": station,
                "down_file": ladcp["down"],
                "up_file": ladcp["up"],
                "ctd_file": ctd_path,
                "xmlcon_path": xmlcon_path,
            })
            unmatched_ctd.discard(Path(ctd_path).stem.replace("TUNSIC", ""))
        else:
            unmatched_ladcp.append(station)
    
    return matched, unmatched_ladcp, list(unmatched_ctd)
