# LADCP Tool Suite — Technical Documentation

**Version 1.0.0** — June 2026

This document describes the methodology, architecture, and implementation details
of the LADCP Tool Suite. It is intended for developers and researchers who need to
understand the processing algorithms, extend the tools, or debug issues.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Data Flow](#data-flow)
3. [CTD Processing Methodology](#ctd-processing-methodology)
4. [LADCP Processing Methodology](#ladcp-processing-methodology)
5. [RDI Binary Format](#rdi-binary-format)
6. [Octave-MATLAB Compatibility](#octave-matlab-compatibility)
7. [GSW Validation](#gsw-validation)
8. [Module Reference](#module-reference)
9. [Testing](#testing)
10. [Extending the Tools](#extending-the-tools)

---

## Architecture

```
ladcp_tool/
├── __init__.py
├── ctd_tool.py              # CLI entry point: CTD processing
├── ladcp_tool.py            # CLI entry point: LADCP processing
├── processors/
│   ├── __init__.py
│   ├── ctd_processor.py     # CNV reader, GSW derived variables, binning
│   ├── rdi_reader.py        # RDI Workhorse PD0 binary format decoder
│   └── ldeo_runner.py       # Octave subprocess launcher for LDEO IX
├── outputs/
│   ├── __init__.py
│   ├── odv_writer.py        # ODV spreadsheet format writer
│   ├── plotter.py           # Matplotlib profile/timeseries plots
│   └── result_writer.py     # ASCII velocity + CTD profile writer
└── utils/
    ├── __init__.py
    └── cast_matcher.py      # LADCP/CTD file matching by station ID
```

### Design Principles

1. **Separation of concerns**: Each module handles one data type (CTD or LADCP)
2. **CLI-first**: Tools are invoked from the command line with standard arguments
3. **Octave as subprocess**: LDEO IX runs in its own Octave process; Python handles
   pre/post-processing, file I/O, and visualization
4. **Open standards**: Output formats follow ODV conventions for interoperability
5. **Fallback modes**: Both tools work with partial data (e.g., CTD without LADCP,
   LADCP without Octave)

### Dependencies

| Component | Library | Purpose |
|-----------|---------|---------|
| CTD processing | `numpy`, `scipy`, `gsw` | Data arrays, interpolation, seawater properties |
| LADCP reading | `struct`, `numpy` | Binary format parsing, velocity masking |
| LDEO processing | GNU Octave, LDEO_IX | Inversion, shear method, ensemble processing |
| Visualization | `matplotlib` | Profile plots, T-S diagrams |
| ODV output | Standard I/O | Tab-separated spreadsheets |
| XML parsing | `xml.etree.ElementTree` | SBE XMLCON calibration coefficients |

---

## Data Flow

```
                     ┌─────────────────┐
                     │  SBE .hex files │  (raw CTD)
                     └────────┬────────┘
                              │ SBEDataProcessing
                              ▼
                     ┌─────────────────┐
    ┌───────────────►│  SBE .cnv files │  (LoopEdit output)
    │                └────────┬────────┘
    │                         │
    │  ┌──────────────────────┼──────────────────────┐
    │  │                      │                      │
    │  ▼                      ▼                      ▼
    │ ctd_tool.py        ladcp_tool.py          ladcp_tool.py
    │ (GSW derived)    (CTD→LDEO ASCII)       (RDI reader)
    │                      │                      │
    │  ┌───────────────────┼──────────────────────┘
    │  │                   ▼
    │  │          ┌─────────────────┐
    │  │          │  Octave LDEO IX │  (inverse + shear)
    │  │          └────────┬────────┘
    │  │                   │
    │  ▼                   ▼
    │  ┌──────────────────────────────────────┐
    │  │          Output Generation            │
    │  │  • ASCII profiles (results/)         │
    │  │  • Plots (plots/)                    │
    │  │  • ODV spreadsheets (odv/)           │
    │  │  • LDEO ASCII (ldeo_ascii/)          │
    │  └──────────────────────────────────────┘
```

---

## CTD Processing Methodology

### CNV File Format

Sea-Bird `.cnv` files consist of:
- **Header** (lines starting with `*` or `#`): metadata, sensor configuration,
  column names, bad flag value
- **Data** (tab-separated numeric columns): one row per scan

The parser (`ctd_processor.read_cnv`) extracts:
- Column names from `# name N = shortname: description` lines
- Bad value flag from `# bad_flag` line
- Sampling interval from `# interval = seconds: X` line
- Position from `* NMEA Latitude/Longitude` lines
- Start time from `* System UpLoad Time` line

Data rows are read as floating-point arrays; values matching the bad flag
(typically `-9.99e-29`) are replaced with NaN.

### GSW Derived Variables

Practical Salinity is computed from conductivity, temperature, and pressure using
the PSS-78 algorithm via `gsw.SP_from_C`:

```
SP = gsw.SP_from_C(C * 10, T, P)  # C in mS/cm
```

**Critical**: The `.cnv` file stores conductivity in **S/m**. GSW expects
**mS/cm**. The conversion factor is **×10**.

Additional derived variables:

| Variable | GSW Function | Description |
|----------|-------------|-------------|
| Absolute Salinity | `SA_from_SP(SP, P, lon, lat)` | TEOS-10 reference salinity |
| Potential Temperature | `pt0_from_t(SA, T, P)` | θ referenced to 0 dbar |
| Conservative Temperature | `CT_from_t(SA, T, P)` | TEOS-10 conservative temperature |
| Sigma-0 | `sigma0(SA, CT)` | Potential density anomaly |
| In-situ Density | `rho(SA, CT, P)` | Density at measurement pressure |
| Sound Speed | `sound_speed(SA, CT, P)` | Chen-Millero via TEOS-10 |
| Depth | `-z_from_p(P, lat)` | Depth in meters (GSW returns negative) |

### Bin Averaging

Data are averaged to a uniform pressure grid:

```
edges = arange(floor(P_min), ceil(P_max) + bin_size, bin_size)
centers = edges[:-1] + bin_size / 2
```

Each bin requires ≥3 valid scans to compute a mean. Bins with fewer scans
are set to NaN and removed from output.

### Validation Against SBE

On cast 975 (0–497 m, 37,792 scans), the GSW pipeline was compared against
SBE Data Processing output:

- **Salinity RMSE**: 0.008 PSU (max difference 0.07 PSU)
- **Density RMSE**: 0.007 kg/m³ (max difference 0.06 kg/m³)
- **Depth RMSE**: 0.0004 m (max difference 0.001 m)

The residual differences are attributed to:
1. SBE uses PSS-78 algorithm implemented in proprietary code
2. GSW uses TEOS-10 thermodynamic functions (more accurate)
3. Small differences in floating-point precision

### LDEO-Compatible Output

Two ASCII files per cast for the LDEO `loadctd.m` / `loadctdprof.m` interface:

**Time series** (`_ctd_timeseries.txt`):
```
elapsed_sec  pressure(dbar)  temperature(°C)  salinity(PSU)
```

**Profile** (`_ctd_profile.txt`):
```
pressure(dbar)  temperature(°C)  salinity(PSU)
```

---

## LADCP Processing Methodology

### RDI Binary Format

The Teledyne RDI Workhorse uses the PD0 binary format. Each ensemble is **664 bytes**:

```
Bytes 0-1:   Header ID (0x7F7F)
Bytes 2-3:   Number of bytes without checksum (662)
Bytes 4-5:   Data source ID
Bytes 6-21:  8 × uint16 data type offsets
Bytes 22+:   Data blocks
Bytes 662-663: Checksum (2 bytes)
```

**Data type blocks** (at their respective offsets):

| Offset | ID | Block | Size |
|--------|-----|-------|------|
| 22 | 0x0000 | Fixed Leader | 60 bytes |
| 81 | 0x0080 | Variable Leader | 67 bytes |
| 146 | 0x0100 | Velocity | 2 + ncells×nbeams×2 bytes |
| 308 | 0x0200 | Correlation | 2 + ncells×nbeams bytes |
| 390 | 0x0300 | Echo Intensity | 2 + ncells×nbeams bytes |
| 472 | 0x0400 | Percent Good | 2 + ncells×nbeams bytes |
| 554 | 0x0600 | Bottom Track | variable |

**Fixed Leader** (key fields, 0-indexed from block start):
- Byte 6: Number of beams (4 for Janus Workhorse)
- Byte 7: Number of cells (20 for this configuration)
- Bytes 8-9: Pings per ensemble (uint16)
- Bytes 10-11: Cell size in cm (uint16)
- Bytes 12-13: Blank after transmit in cm (uint16)

**Variable Leader** (key fields, 2 bytes after 0x0080 ID):
- Bytes 2-8: RTC (year, month, day, hour, minute, second, hundredths)
- Bytes 10-11: BIT result (uint16)
- Bytes 12-13: Speed of sound (uint16, m/s)
- Bytes 14-15: Transducer depth (uint16, dm)
- Bytes 16-17: Heading (uint16, hundredths °)
- Bytes 18-19: Pitch (int16, hundredths °)
- Bytes 20-21: Roll (int16, hundredths °)
- Bytes 22-23: Salinity (uint16, ppt)
- Bytes 24-25: Temperature (uint16, hundredths °C)

**Velocity data**: int16 array, (mm/s → m/s by dividing by 1000).
Invalid values (RDIs sentinel = -32768, producing -32.768 m/s) are masked.

### LDEO IX Processing Pipeline

The LDEO IX software implements the Visbeck (2002) lowered ADCP velocity
profiling method in 17 steps:

| Step | Module | Algorithm |
|------|--------|-----------|
| 1 | `loadrdi.m` | Read RDI binary, decode frequencies, beam→Earth transform, initial QC |
| 2 | `fixcompass.m` | Compass bias correction |
| 3 | `loadnav.m` | GPS navigation (optional) |
| 4 | `getbtrack.m` | Bottom tracking via RDI ranges + acoustic backscatter |
| 5 | `loadctdprof.m` | Load binned CTD profile (P, T, S) |
| 6 | `loadctd.m` | Load CTD time series, cross-correlate W for time lag |
| 7 | `getdpth.m` | Depth from vertical velocity integration + bottom constraint |
| 8 | `uvwrot.m` | Tilt correction (pitch/roll rotation) |
| 9 | `edit_data.m` | Error velocity, tilt, side-lobe, outlier removal |
| 10 | `prepinv.m` | Super-ensemble formation (depth binning) |
| 11 | `getinv.m` | Outlier removal using initial solution |
| 12 | `prepinv.m` | Re-form super-ensembles with refined solution |
| 13 | `loadsadcp.m` | Ship-mounted ADCP data (optional) |
| 14 | `getinv.m` | **Inverse solution** — weighted least-squares velocity profile |
| 15 | `calc_shear3.m` | **Shear method** — baroclinic velocity from vertical shear |
| 16 | `plotinv.m` | Diagnostic plots (stubbed in Octave) |
| 17 | `savearch.m` | Save structured ASCII results (8 sections) |

#### Inverse Solution (Step 14)

The core algorithm solves:

```
A · x = b
```

where:
- **A** is the design matrix encoding: velocity constraints, shear constraints,
  bottom-track constraints, barotropic constraint
- **x** is the unknown velocity profile (u, v at each depth level)
- **b** is the observation vector

The matrix is solved via Cholesky decomposition or Moore-Penrose pseudoinverse
(controlled by `ps.solve`). The solution provides both the absolute velocity
profile and error estimates.

#### Shear Method (Step 15)

Computes vertical shear ∂u/∂z from super-ensemble velocity differences,
averages into regular depth intervals, and integrates from a reference
level (bottom or surface):

```
u(z) = u(z_ref) + ∫_{z_ref}^{z} (∂u/∂z') dz'
```

Provides an independent estimate of the baroclinic velocity field.

### Time Synchronization

The `bestlag` algorithm cross-correlates the vertical velocity (W) measured
by the ADCP with W computed from CTD pressure time series. The lag (in
ensemble counts) that maximizes correlation is applied to align the clocks.

For the TUNSIC26 data, the best lag was typically −129 scans (~5.4 seconds)
with correlation coefficients >0.99.

### Super-Ensemble Formation

Raw ADCP ensembles are averaged into "super-ensembles" at regular depth
intervals (default: 5 m). This reduces the 1300+ raw ensembles per cast
to ~30-100 super-ensembles, each representing an average velocity profile
over a small depth range. The `prepinv.m` module handles this with:

1. Vertical gridding of instrument depth from CTD
2. Weighted averaging of velocity profiles within each depth bin
3. Heading offset computation between master and slave instruments

---

## Octave-MATLAB Compatibility

The LDEO IX code was originally written for MATLAB. The following patches were
applied for GNU Octave 8.4.0 compatibility:

| Issue | Original | Patch | Files |
|-------|----------|-------|-------|
| `interp1q` missing | `interp1q(x, y, xi)` | → `interp1(x, y, xi)` | `loadctd.m`, `getinv.m`, plus 6 others |
| Reserved keyword `do` | `do = d` | → `d_orig = d` | `getinv.m` |
| XLSX reading | `gh = xlsread(fname)` | → `load(fname, 'gh')` | `magdev.m` |
| CTD position | `error('no position')` | → fallback to `p.poss` | `loadctdprof.m` |
| Plot escapes | MATLAB console escapes | → stubbed with `disp` | `plotraw.m` |
| `fill()` args | MATLAB-specific | → stubbed | `plotinv.m`, `checkbtrk.m`, `checkinv.m` |
| `bar(...,'stack')` | → `bar(...,'stacked')` | stubbed | `checkinv.m` |
| `pcolorn` | MATLAB-specific colormap | → stubbed | `pcolorn.m` |
| `savearch` diagnostics | Complex struct output | → structured 8-section ASCII writer | `savearch.m` |

The patched files are in `TUNSIC26/04-LDEO-IX/patched/`. The original files
are preserved in `TUNSIC26/04-LDEO-IX/original/`.

### Magnetic Declination

The `magdev.m` function computes magnetic declination from the IGRF-13 model.
In Octave headless mode, `xlsread` cannot use COM/ActiveX. The coefficients
were converted from the IGRF13 XLSX file to a `.mat` file using `openpyxl`:

```python
import openpyxl, scipy.io
wb = openpyxl.load_workbook('IGRF13coeffs.xlsx')
# Extract 196 × 26 numeric matrix (years 1900–2025 + secular variation)
arr = ...
scipy.io.savemat('IGRF13coeffs.mat', {'gh': arr})
```

### IGRF-13 Model

For dates beyond the model's definitive range (2026 > 2025), `magdev` uses
linear extrapolation with secular variation coefficients. The computed
magnetic declination for the TUNSIC26 survey area (36.4°N, 14.75°E) in
2026 is approximately 4.1°E.

---

## RDI Binary Format — Discovery Notes

The RDI WH300 binary format was reverse-engineered from raw hex dumps because
documentation for this specific firmware version was unavailable. Key findings:

1. **Ensemble size**: 664 bytes (not 662 as the header suggests — the 2-byte
   checksum adds 2 bytes)
2. **Header layout**: 11 × uint16 words, not the documented 6-word structure
3. **Fixed Leader**: Includes a 2-byte data type ID (0x0000) at the block
   start, unlike some documented versions. Body is 58 bytes, not 42.
4. **Variable Leader**: 2-byte ID (0x0080) + data. Body is 63 bytes (vs 65
   documented), with heading at bytes 16-17, pitch at 18-19 (int16).
5. **Firmware version**: Stored as raw byte values (0x4d=77, 0x08=8 →
   77.8), not BCD-encoded.

These differences account for the instrument being a Workhorse Monitor
(WH300) with firmware 77.8, which uses a slightly different PD0 layout
from the standard Workhorse Sentinel.

---

## Module Reference

### `processors/ctd_processor.py`

```python
read_cnv(filepath) → (array, meta_dict)
    Parse SBE .cnv file header and data.

extract_ctd(array, meta) → dict
    Extract P, T, C, position, elapsed time from CNV data.

isolate_downcast(ctd_data) → dict
    Extract downcast only: median-filter max pressure + monotonicity filter.
    Adds n_scans_raw, n_scans_downcast, p_max_index, upcast_excluded,
    monotonicity_violations.

check_pressure_monotonicity(ctd_data, fix=True) → dict
    Standalone pressure inversion detection/removal (for upcast mode).

compute_derived(ctd_data) → dict
    Compute GSW-derived variables: salinity, pot_temp, sigma0, density,
    sound_speed, depth. Returns masked arrays with good_mask.

bin_profile(ctd_data, derived, bin_size=1.0) → dict
    Average CTD data to uniform pressure bins.

bin_profile_depth(ctd_data, derived, bin_size_m=1.0) → dict
    Average CTD data to uniform depth bins (meters, via GSW z_from_p).

compute_ctd_qf(binned, ranges=None) → dict
    Assign ODV/SeaDataNet quality flags (MEDITERRANEAN_RANGES constant).
    Returns '{var}_qf' arrays (QF 1/3/4/9).

save_ldeo_format(ctd_data, derived, prefix, output_dir) → binned_dict
    Write LDEO-compatible ASCII time series + profile files.
```

### `processors/rdi_reader.py`

```python
class RDIFile(filepath):
    __len__() → int                  # number of ensembles
    __iter__() → yield dict          # iterate over ensembles
    read(idx) → dict or None         # read single ensemble
    read_all() → dict                # all ensembles as structured arrays

    # Ensemble dict keys:
    #   datetime, heading, pitch, roll, temperature, salinity,
    #   depth_xdcr, velocity (ndarray[4,20]), correlation, echo_intensity,
    #   percent_good, n_cells, n_beams, cell_size, blank, bin1_dist
```

Binary parsing constants:
- `ENSEMBLE_SIZE = 664` (bytes)
- Frequency-to-velocity: `mm/s → m/s` via `× 0.001`
- Masked value: `vel < -30.0` (RDIs sentinel = -32768 mm/s)

### `processors/ldeo_runner.py`

```python
create_set_cast_params(cast, work_dir, output_prefix) → Path
    Generate Octave set_cast_params.m for a cast.

run_octave_processing(cast, work_dir, timeout=600, max_memory_mb=0,
                      avdz=None, stream_output=True) → (success, message, error_type)
    Execute Octave processing as subprocess. Monitors RSS memory,
    classifies errors (MEMORY, MATRIX_DIM, SINGULAR, TIMEOUT, etc.).

run_octave_with_retry(cast, work_dir, timeout=600, max_memory_mb=0,
                      avdz_sequence=None, stream_output=True) → (success, message, error_type, avdz_used)
    Adaptive retry with progressively larger avdz on memory failures.

read_ldeo_result(result_file) → dict
    Parse LDEO structured ASCII output (8 sections). Returns dict with
    'header', 'velocity', 'shear', 'updown', 'ctd', 'range', 'diagnostics',
    'bottom_track', 'warnings'. Backward-compatible: exposes depth/u/v/
    uerr/speed at top level when [VELOCITY] is present. Old-format files
    (no section markers) parse correctly as VELOCITY.

extract_processing_warnings(result) → list[str]
    Extract warnings from result dict. Derives HIGH_ERROR (mean>0.10 m/s)
    and HEADING_OFFSET (>10 deg) from diagnostics/header.
```

### `utils/cast_matcher.py`

```python
find_ladcp_files(source_dir) → {station: {down_path, up_path}}
    Scan directory for MASTE*/SLAVE* .000 files.

find_ctd_files(source_dir) → {station: cnv_path}
    Scan directory for .cnv files, strip TUNSIC suffix.

match_casts(ladcp, ctd, xmlcon=None) → (matched, unmatched_ladcp, unmatched_ctd)
    Match by station ID with prefix/suffix normalization.
```

### `outputs/odv_writer.py`

```python
write_odv_collection(casts, output_dir, cruise_id)
    Write ODV collection file + per-station spreadsheets.

write_cast_odv(cast, output_dir, cruise_id)
    Write single-station ODV spreadsheet (tab-separated).
    15 columns: Pressure, Depth, Temperature, QF:Temperature, Salinity,
    QF:Salinity, SigmaTheta, QF:SigmaTheta, SoundSpeed, U, QF:U, V,
    QF:V, U_Error, PotTemp.

compute_velocity_qf(result, threshold_good=0.05, threshold_warn=0.10) → dict
    Assign quality flags to LADCP velocity based on inversion error
    and physical plausibility (VELOCITY_QF_THRESHOLDS module constant).
```

ODV format requirements:
- Header starts with `//` comments
- Collection: `Cruise\tStation\tType\tDate\tLongitude\tLatitude\tBot. Depth`
- Spreadsheet: Variable declarations (`// <Variable name="...">`) + column headers + data

### `outputs/plotter.py`

```python
plot_velocity_profile(ladcp, cast_id, dir, dpi=120) → Path
    3-panel velocity plot: U, V, Speed vs depth.

plot_ctd_profile(ctd, cast_id, dir, dpi=120) → Path
    3-panel CTD plot: T-S diagram, T/S profiles, σ₀/sound speed.

plot_combined(ctd, ladcp, cast_id, dir, dpi=120) → Path
    4-panel combined: velocity + T-S + T/S profiles + σ₀/SS.
```

All plots use `matplotlib.use('Agg')` for headless operation.

### `outputs/result_writer.py`

```python
write_velocity_profile(ladcp, cast_id, dir) → Path
    ASCII velocity profile: depth, u, v, err, speed.

write_summary(all_results, dir, cruise_id) → Path
    Multi-cast summary table: depth, velocity ranges, errors, status.
```

---

## Testing

### CTD Tool Validation

```bash
# Run on test data
python ladcp_tool/ctd_tool.py \
    -s /home/rocco/ProcessedCTD/07-LoopEdit \
    -o /tmp/ctd_test \
    --no-odv --no-plots
```

**Expected**: 19/20 profiles generated. Cast 641 fails with boolean index mismatch
(1 extra bad value in data). All other casts produce valid profiles.

### LADCP Tool Validation

```bash
python ladcp_tool/ladcp_tool.py \
    -s /home/rocco/LADCP \
    --ctd-dir /home/rocco/ProcessedCTD/07-LoopEdit \
    -o /tmp/ladcp_test \
    --no-odv --no-plots --timeout 300
```

**Expected**: 10/16 velocity profiles generated. Casts 299/987/T849/T918/T921/T846
fail with inversion matrix errors on 2 GB RAM.

### LADCP+CTD End-to-End (Deep Cast)

On cast 975 (497 m depth):
- CTD: 37,792 scans → 501 binned levels
- LADCP: ~2,700 ensembles → 99 velocity levels
- Inversion error: 0.047 m/s
- Total processing time: ~15 seconds

---

## Extending the Tools

### Adding a New Instrument

1. **CTD sensor**: Add a new `Sensor` subclass in `ctd_processor.py` with a
   `convert(raw_value)` method. Update `parse_xmlcon()` to detect the sensor ID.
2. **LADCP format**: Modify `RDIFile` constants if ensemble size or data block
   offsets differ from the WH300 layout.

### Adding a New Output Format

Implement a writer module in `outputs/` following the `odv_writer.py` pattern:
- Accept a list of cast dicts
- Output files to a directory
- Call from `ctd_tool.py` / `ladcp_tool.py` main() under a new `--format` flag

### Replacing Octave with Pure Python

The LDEO pipeline could be re-implemented in Python using:
- `scipy.sparse.linalg` for the inverse solution
- `numpy` for the shear method
- The existing `rdi_reader.py` for binary parsing

This would eliminate the Octave dependency and enable cross-platform deployment.
The key algorithms (prepinv, getinv, calc_shear3) are well-documented in the
MATLAB source code and the Visbeck (2002) paper.

### Adding Support for Other CTD Formats

The `ctd_processor.read_cnv` function can be extended to support:
- `.btl` (bottle files) using the SBE bottle format parser
- `.edf` (exchange data format)
- Raw `.hex` files with the SBE calibration formulas

---

## References

1. Visbeck, M. (2002). "Deep velocity profiling using lowered acoustic Doppler
   current profilers: Bottom track and inverse solutions." *J. Atmos. Oceanic
   Technol.*, 19, 794–807.
2. Thurnherr, A.M. (2024). "LDEO LADCP Processing Software, Version IX_15."
   GitHub: `athurnherr/LDEO_IX`.
3. Firing, E. and Hummon, J.M. (2010). "pycurrents: Python tools for
   oceanographic data processing." University of Hawaii.
4. McDougall, T.J. and Barker, P.M. (2011). "Getting started with TEOS-10 and
   the Gibbs Seawater (GSW) Oceanographic Toolbox." SCOR/IAPSO WG127.
5. Alken, P. et al. (2021). "International Geomagnetic Reference Field: the
   thirteenth generation." *Earth Planets Space*, 73, 49.
6. Teledyne RD Instruments (2020). "Workhorse Commands and Output Data Format."
   P/N 957-6156-00.
7. Sea-Bird Electronics (2024). "SBE Data Processing Manual."
   seabird.com/software.
