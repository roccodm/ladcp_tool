# ladcp_tool/processors/ldeo_runner.py
"""Run LDEO IX LADCP processing via GNU Octave subprocess."""

import subprocess
import shutil
import os
from pathlib import Path

OCTAVE_CMD = shutil.which('octave') or 'octave'

# Auto-detect LDEO paths relative to this module (bundled with package)
_LDEO_ROOT = Path(__file__).resolve().parent.parent / 'ldeo'
LDEO_PATCHED = _LDEO_ROOT / 'patched'
LDEO_GEOMAG = _LDEO_ROOT / 'geomag'

# Fallback: environment variable override
if os.environ.get('LDEO_PATCHED'):
    LDEO_PATCHED = Path(os.environ['LDEO_PATCHED'])
if os.environ.get('LDEO_GEOMAG'):
    LDEO_GEOMAG = Path(os.environ['LDEO_GEOMAG'])


def create_set_cast_params(cast, work_dir, output_prefix):
    """Create set_cast_params.m for a cast using the bundled template."""
    from datetime import datetime
    
    # Locate template
    template_path = Path(__file__).resolve().parent.parent / 'templates' / 'set_cast_params.template'
    if template_path.exists():
        template = template_path.read_text()
    else:
        template = _fallback_template()
    
    station = cast['station']
    replacements = {
        '{{STATION}}': station,
        '{{CRUISE_ID}}': cast.get('cruise_id', 'UNKNOWN'),
        '{{TIMESTAMP}}': datetime.now().isoformat(),
        '{{DOWN_FILE}}': cast['down_file'] or ' ',
        '{{UP_FILE}}': cast['up_file'] or ' ',
        '{{CTD_TIMESERIES}}': cast.get('ctd_timeseries', ' '),
        '{{CTD_PROFILE}}': cast.get('ctd_profile', ' '),
        '{{RESULT_PREFIX}}': output_prefix,
        '{{LAT}}': f"{cast.get('lat', 36.4):.4f}",
        '{{LON}}': f"{cast.get('lon', 14.75):.4f}",
    }
    
    script = template
    for key, val in replacements.items():
        script = script.replace(key, val)
    
    filepath = Path(work_dir) / f"set_cast_params_{station}.m"
    filepath.write_text(script)
    return filepath


def _fallback_template():
    """Inline template if file not found."""
    return """% set_cast_params.m for cast {{STATION}}
p.name = 'cast_{{STATION}}';
p.software = 'LDEO LADCP software: Version IX_15';
f.ladcpdo = '{{DOWN_FILE}}';
f.ladcpup = '{{UP_FILE}}';
f.ctd = '{{CTD_TIMESERIES}}';
f.ctdprof = '{{CTD_PROFILE}}';
f.nav = ' ';
f.sadcp = ' ';
f.res = '{{RESULT_PREFIX}}';
f.checkpoints = '.ckpt_{{STATION}}';
f.ctd_header_lines = 0;
f.ctd_fields_per_line = 4;
f.ctd_time_field = 1;
f.ctd_pressure_field = 2;
f.ctd_temperature_field = 3;
f.ctd_salinity_field = 4;
f.ctd_time_base = 0;
f.ctd_badvals = -9e99;
p.ladcp_station = 0;
p.ladcp_cast = 1;
p.cruise_id = '{{CRUISE_ID}}';
p.whoami = 'ladcp_tool';
p = setdefv(p, 'poss', [{{LAT}} 0 {{LON}} 0]);
p = setdefv(p, 'pose', [{{LAT}} 0 {{LON}} 0]);
p.getdepth = 1; p.btrk_mode = 1; p.ctdtime = 1;
p.rotup2down = 0; p.offsetup2down = 0; p.fix_compass = 0;
p.soundcorr = 1; p.drot = NaN;
p = setdefv(p, 'zpar', [0 NaN 0]);
p.elim = 0.5; p.vlim = 2.5; p.pglim = 0;
p.wlim = 0.20; p.tiltmax = [22 4]; p.ambiguity = 2.5;
p.outlier = [4.0 3.0]; p.outlier_n = 100; p.avdz = 5;
p.single_ping_accuracy = NaN;
p = setdefv(p, 'down_sn', 0); p = setdefv(p, 'up_sn', 0);
p.saveplot = []; p.saveplot_png = []; p.saveplot_pdf = [];
p.savemat = 0; p.savecdf = 0;
p.dn_range = [0 0 0 0]; p.up_range = [0 0 0 0];
p.xmv = [0 0]; p.xmc = [0 0]; p.tint = [0 0];
p.sv = [0 0]; p.temp = [0 0];
p.btrk_u_bias = 0; p.btrk_v_bias = 0;
p.warnp = ' '; p.warn = ' ';
"""


def run_octave_processing(cast, work_dir, timeout=600):
    """Run Octave LDEO processing for a single cast.
    
    Returns True if successful, False otherwise.
    """
    station = cast['station']
    work = Path(work_dir)
    script = work / f"process_{station}.m"
    
    # Create driver script
    script.write_text(f"""pkg load io;
pkg load statistics;
addpath('{LDEO_PATCHED}');
addpath('{LDEO_GEOMAG}');
cd('{work}');
clear f p d dr ds ps di de der att;
clear set_cast_params;
% Copy per-cast params to the standard name expected by process_cast
copyfile('set_cast_params_{station}.m', 'set_cast_params.m');
process_cast('{station}', 1, 0);
""")
    
    try:
        result = subprocess.run(
            [OCTAVE_CMD, '--no-gui', str(script)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(work),
        )
        # Check for saved result file
        out_file = work / f"result_{station}_profile.txt"
        success = out_file.exists()
        return success, result.stdout[-2000:] if not success else result.stdout[-500:]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def read_ldeo_result(result_file):
    """Read LDEO result profile, return (depth, u, v, uerr) arrays."""
    import re
    with open(result_file) as f:
        lines = f.readlines()
    
    z, u, v, err = [], [], [], []
    for line in lines:
        if line.startswith('#'):
            continue
        try:
            vals = [float(x) for x in line.split()]
            if len(vals) >= 4:
                z.append(vals[0])
                u.append(vals[1])
                v.append(vals[2])
                err.append(vals[3])
        except ValueError:
            continue
    
    return {
        'depth': np.array(z), 'u': np.array(u), 'v': np.array(v),
        'uerr': np.array(err),
    }


import numpy as np
