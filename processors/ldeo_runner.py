# ladcp_tool/processors/ldeo_runner.py
"""Run LDEO IX LADCP processing via GNU Octave subprocess."""

import subprocess
import shutil
import os
import signal
import time
import threading
import numpy as np
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

# Memory thresholds (bytes)
_DEFAULT_MEM_LIMIT_MB = 0  # 0 = no limit; set via --max-memory


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


def _estimate_memory_mb(cast):
    """Estimate memory needed for processing based on input file size."""
    down = cast.get('down_file')
    if not down or not Path(down).exists():
        return 0
    file_size_mb = Path(down).stat().st_size / (1024 * 1024)
    up = cast.get('up_file')
    if up and Path(up).exists():
        file_size_mb += Path(up).stat().st_size / (1024 * 1024)
    # Empirical: Octave uses ~30-50x the raw file size in RAM
    return int(file_size_mb * 50)


def _get_available_memory_mb():
    """Get available system memory in MB."""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return 0


def _get_process_memory_mb(pid):
    """Get RSS memory usage of a process in MB."""
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, FileNotFoundError):
        pass
    return 0


def _classify_error(stdout, stderr, exit_code):
    """Classify Octave error by type for actionable diagnostics."""
    combined = (stdout or '') + (stderr or '')
    lower = combined.lower()

    if 'out of memory' in lower or 'cannot allocate' in lower:
        return 'MEMORY', 'Out of memory — try increasing p.avdz or system RAM'
    if 'nonconformant arguments' in lower or 'operator *' in lower:
        return 'MATRIX_DIM', 'Matrix dimension mismatch — likely memory-related, try larger p.avdz'
    if 'singular matrix' in lower or 'matrix singular' in lower:
        return 'SINGULAR', 'Singular matrix in inverse — data quality issue'
    if 'error:' in lower and 'undefined' in lower:
        return 'MISSING_FUNC', 'Missing Octave function — check LDEO path setup'
    if 'error:' in lower and ('file' in lower or 'open' in lower):
        return 'FILE_IO', 'File I/O error — check input paths'
    if exit_code == -9 or exit_code == -signal.SIGKILL:
        return 'OOM_KILLED', 'Process killed by OOM killer — increase system RAM'
    if exit_code != 0:
        return 'OCTAVE_ERROR', f'Octave exited with code {exit_code}'
    return 'UNKNOWN', 'Unknown error'


def _build_octave_script(station, work, avdz=None):
    """Build the Octave driver script with memory optimizations."""
    avdz_override = ''
    if avdz is not None and avdz != 5:
        avdz_override = f"p.avdz = {avdz};\n"

    return f"""pkg load io;
pkg load statistics;
addpath('{LDEO_PATCHED}');
addpath('{LDEO_GEOMAG}');
cd('{work}');
clear f p d dr ds ps di de der att;
clear set_cast_params;
% Copy per-cast params to the standard name expected by process_cast
copyfile('set_cast_params_{station}.m', 'set_cast_params.m');
rehash;
{avdz_override}process_cast('{station}', 1, 0);
"""


def run_octave_processing(cast, work_dir, timeout=600, max_memory_mb=0,
                          avdz=None, stream_output=True):
    """Run Octave LDEO processing for a single cast.

    Args:
        cast: dict with station info and file paths
        work_dir: working directory for Octave
        timeout: max seconds before killing the process
        max_memory_mb: if >0, kill process when RSS exceeds this (MB)
        avdz: override for super-ensemble vertical spacing (larger = less memory)
        stream_output: if True, stream output line-by-line for monitoring

    Returns:
        (success, message, error_type) tuple
    """
    station = cast['station']
    work = Path(work_dir)
    script = work / f"process_{station}.m"

    script.write_text(_build_octave_script(station, work, avdz))

    # Estimate and report memory needs
    est_mem = _estimate_memory_mb(cast)
    avail_mem = _get_available_memory_mb()
    if est_mem > 0:
        print(f"  Memory estimate: ~{est_mem} MB needed, {avail_mem} MB available")
        if est_mem > avail_mem * 0.8 and avail_mem > 0:
            print(f"  WARNING: Estimated memory ({est_mem} MB) near available ({avail_mem} MB)")

    output_lines = []
    error_type = 'UNKNOWN'
    process = None
    monitor_thread = None
    killed_by_monitor = threading.Event()

    try:
        process = subprocess.Popen(
            [OCTAVE_CMD, '--no-gui', str(script)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(work),
        )

        # Memory monitor thread
        if max_memory_mb > 0:
            def _memory_monitor():
                while process.poll() is None:
                    rss = _get_process_memory_mb(process.pid)
                    if rss > max_memory_mb:
                        print(f"  MEMORY LIMIT: Octave using {rss} MB > {max_memory_mb} MB limit")
                        killed_by_monitor.set()
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        except (ProcessLookupError, PermissionError):
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                        return
                    time.sleep(2)

            monitor_thread = threading.Thread(target=_memory_monitor, daemon=True)
            monitor_thread.start()

        # Stream output with timeout
        deadline = time.monotonic() + timeout
        for line in process.stdout:
            line = line.rstrip('\n')
            output_lines.append(line)
            if stream_output and line.strip():
                # Show key progress indicators
                if any(kw in line for kw in [
                    'LOADRDI:', 'PREPINV:', 'GETINV:', 'EDIT_DATA:',
                    'process_cast', 'inverse', 'shear', 'save',
                    'WARNING', 'error', 'ERROR', 'super ensemble',
                    'velocity error', 'TIMEOUT', 'memory',
                ]):
                    print(f"    octave: {line[:120]}")
            if time.monotonic() > deadline:
                print(f"  TIMEOUT after {timeout}s")
                process.kill()
                process.wait()
                return False, f"TIMEOUT after {timeout}s", 'TIMEOUT'

        process.wait()

        if killed_by_monitor.is_set():
            return False, f"Killed: memory exceeded {max_memory_mb} MB", 'MEMORY_LIMIT'

        # Check for result file
        out_file = work / f"result_{station}_profile.txt"
        if out_file.exists():
            return True, '\n'.join(output_lines[-20:]), 'SUCCESS'

        # Failed — classify the error
        full_output = '\n'.join(output_lines)
        error_type, error_msg = _classify_error(full_output, '', process.returncode)

        # Return more output on failure for diagnostics
        tail = '\n'.join(output_lines[-50:])
        return False, f"[{error_type}] {error_msg}\n---\n{tail}", error_type

    except FileNotFoundError:
        return False, f"Octave not found at {OCTAVE_CMD}", 'NO_OCTAVE'
    except Exception as e:
        return False, str(e), 'EXCEPTION'
    finally:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    process.kill()
                    process.wait(timeout=3)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass


def run_octave_with_retry(cast, work_dir, timeout=600, max_memory_mb=0,
                          avdz_sequence=None, stream_output=True):
    """Run Octave processing with adaptive retry on memory failures.

    If the first attempt fails with a memory-related error, retries with
    progressively larger avdz values to reduce matrix dimensions.

    Args:
        cast: dict with station info and file paths
        work_dir: working directory
        timeout: seconds per attempt
        max_memory_mb: memory limit per attempt (0 = unlimited)
        avdz_sequence: list of avdz values to try, e.g. [5, 10, 15]
        stream_output: whether to print Octave progress

    Returns:
        (success, message, error_type, avdz_used) tuple
    """
    if avdz_sequence is None:
        avdz_sequence = [None]  # use default from set_cast_params

    memory_errors = {'MEMORY', 'MATRIX_DIM', 'OOM_KILLED', 'MEMORY_LIMIT'}

    for attempt, avdz in enumerate(avdz_sequence):
        if attempt > 0:
            print(f"  Retry {attempt}/{len(avdz_sequence)-1} with avdz={avdz} m")

        success, msg, err_type = run_octave_processing(
            cast, work_dir, timeout=timeout, max_memory_mb=max_memory_mb,
            avdz=avdz, stream_output=stream_output,
        )

        if success:
            return True, msg, 'SUCCESS', avdz

        if err_type not in memory_errors:
            return False, msg, err_type, avdz

        # Memory error — try next avdz if available
        if attempt < len(avdz_sequence) - 1:
            print(f"  Memory error with avdz={avdz}, will retry with larger bin spacing")

    return False, msg, err_type, avdz_sequence[-1]


def read_ldeo_result(result_file):
    """Parse LDEO structured ASCII output.

    Il file e' organizzato in sezioni delimitate da marcatori [NOME].
    Ogni sezione contiene commenti (righe con #) e dati tabulari.
    Retrocompatibile: espone depth/u/v/uerr/speed al primo livello
    quando la sezione [VELOCITY] e' presente.

    Returns:
        dict con le sezioni:
            'header': dict di metadati (chiave: valore)
            'velocity': dict con arrays depth, u, v, uerr[, w, speed] (o None)
            'shear': dict con arrays depth, u_shear, v_shear (o None)
            'updown': dict con arrays depth, u_do, v_do, u_up, v_up (o None)
            'ctd': dict con arrays depth, pressure, temperature, salinity[, ss, n2] (o None)
            'range': dict con arrays depth, range[, range_do, range_up] (o None)
            'diagnostics': dict di metriche (chiave: valore)
            'bottom_track': dict (o None)
            'warnings': list di stringhe warning
    """
    result = {
        'header': {}, 'velocity': None, 'shear': None,
        'updown': None, 'ctd': None, 'range': None,
        'diagnostics': {}, 'bottom_track': None,
        'warnings': [],
    }

    with open(result_file) as f:
        lines = f.readlines()

    current_section = 'VELOCITY'  # default for old-format files (no markers)
    data_lines = []
    in_warnings_block = False

    def flush_section():
        nonlocal data_lines, current_section
        if current_section is None or not data_lines:
            data_lines = []
            return

        arr = np.array(data_lines, dtype=float)

        if current_section == 'VELOCITY':
            r = {'depth': arr[:, 0], 'u': arr[:, 1],
                 'v': arr[:, 2], 'uerr': arr[:, 3]}
            if arr.shape[1] > 4:
                r['w'] = arr[:, 4]
            r['speed'] = np.sqrt(r['u']**2 + r['v']**2)
            result['velocity'] = r

        elif current_section == 'SHEAR':
            result['shear'] = {
                'depth': arr[:, 0], 'u_shear': arr[:, 1],
                'v_shear': arr[:, 2]}

        elif current_section == 'UPDOWN':
            result['updown'] = {
                'depth': arr[:, 0],
                'u_do': arr[:, 1], 'v_do': arr[:, 2],
                'u_up': arr[:, 3], 'v_up': arr[:, 4]}

        elif current_section == 'CTD':
            r = {'depth': arr[:, 0], 'pressure': arr[:, 1],
                 'temperature': arr[:, 2], 'salinity': arr[:, 3]}
            if arr.shape[1] > 4:
                r['sound_speed'] = arr[:, 4]
            if arr.shape[1] > 5:
                r['n2'] = arr[:, 5]
            result['ctd'] = r

        elif current_section == 'RANGE':
            r = {'depth': arr[:, 0], 'range': arr[:, 1]}
            if arr.shape[1] > 2:
                r['range_do'] = arr[:, 2]
            if arr.shape[1] > 3:
                r['range_up'] = arr[:, 3]
            result['range'] = r

        data_lines = []

    for line in lines:
        raw = line.rstrip('\n')
        s = line.strip()

        if s.startswith('[') and s.endswith(']'):
            flush_section()
            current_section = s[1:-1]
            in_warnings_block = False
            continue

        if s.startswith('#'):
            content = s[1:].strip()

            if content == 'Warnings:':
                in_warnings_block = True
                continue

            # Warning continuation: 2+ spaces after '#' in the raw line
            is_warning_line = len(raw) > 1 and raw[1:3] == '  '
            if is_warning_line and in_warnings_block:
                result['warnings'].append(content)
                continue

            # Parsing chiave: valore per HEADER / DIAGNOSTICS / BOTTOM_TRACK
            if ':' in content and current_section in (
                    'HEADER', 'DIAGNOSTICS', 'BOTTOM_TRACK'):
                key, _, val = content.partition(':')
                key = key.strip()
                val = val.strip()
                try:
                    val = float(val)
                except ValueError:
                    pass

                if current_section == 'HEADER':
                    result['header'][key] = val
                elif current_section == 'DIAGNOSTICS':
                    result['diagnostics'][key] = val
                elif current_section == 'BOTTOM_TRACK':
                    if result['bottom_track'] is None:
                        result['bottom_track'] = {}
                    result['bottom_track'][key] = val
            continue

        if s and not s.startswith('#'):
            try:
                vals = [float(x) for x in s.split()]
                if vals:
                    data_lines.append(vals)
            except ValueError:
                continue

    flush_section()

    # Retrocompatibilita': esponi depth/u/v/uerr/speed al primo livello
    if result['velocity']:
        for k in ('depth', 'u', 'v', 'uerr', 'speed'):
            result[k] = result['velocity'][k]

    return result


def extract_processing_warnings(result):
    """Estrae i warning dal result dict per inclusione nel summary.

    Returns:
        list di stringhe brevi (max 80 char ciascuna)
    """
    warnings = list(result.get('warnings', []))
    diag = result.get('diagnostics', {})

    mean_err = diag.get('MeanError_m/s', 0)
    if isinstance(mean_err, (int, float)) and mean_err > 0.10:
        warnings.append(f'HIGH_ERROR: mean={mean_err:.3f} m/s')

    heading_off = result.get('header', {}).get('HeadingOffset_deg', 0)
    if isinstance(heading_off, (int, float)) and abs(heading_off) > 10:
        warnings.append(f'HEADING_OFFSET: {heading_off:.1f} deg')

    return warnings
