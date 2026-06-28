# LADCP Tool Suite — User Guide

**Version 1.0.0** — June 2026

The LADCP Tool Suite provides an open-source, command-line pipeline for processing
Lowered ADCP (LADCP) and CTD data from oceanographic cruises. It produces velocity
profiles, CTD-derived variables, publication-ready plots, and ODV-compatible
spreadsheets — all from raw instrument files without commercial software dependencies.

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [ctd_tool — CTD Processing](#ctd_tool)
5. [ladcp_tool — LADCP Processing](#ladcp_tool)
6. [Output Description](#output-description)
7. [ODV Compatibility](#odv-compatibility)
8. [Troubleshooting](#troubleshooting)
9. [Examples](#examples)

---

## Overview

The suite consists of two independent tools:

| Tool | Input | Output | Purpose |
|------|-------|--------|---------|
| `ctd_tool` | SBE `.cnv` files | CTD profiles, T-S plots, ODV files | Process CTD data with GSW |
| `ladcp_tool` | RDI `.000` + CTD `.cnv` | Velocity profiles, velocity plots, ODV files | Process LADCP data with LDEO IX |

**Instruments supported:**
- **CTD**: Sea-Bird SBE 9/11+/19/25 (via `.cnv` files from DatCnv or later processing)
- **LADCP**: Teledyne RDI Workhorse (300 kHz, Master/Slave configuration)
- **Software stack**: Python 3.12 + GSW + NumPy/SciPy + GNU Octave + LDEO IX

---

## Installation

### System Requirements

- **OS**: Linux (Ubuntu 24.04 recommended)
- **RAM**: 4 GB minimum (8 GB for deep casts >500 m)
- **Python**: 3.12+
- **Octave**: 8.4+

### 1. System Packages

```bash
sudo apt install -y build-essential gfortran python3.12-venv python3-dev \
    libhdf5-dev libnetcdf-dev octave octave-statistics octave-io
```

### 2. Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install numpy scipy matplotlib netCDF4 gsw cftime openpyxl
```

### 3. LDEO IX Software

The LADCP tool requires the LDEO IX processing code (patched for Octave):

```bash
# Option A: From the TUNSIC26 tarball
tar xzf TUNSIC26.tar.gz

# Option B: From GitHub + apply patches
git clone https://github.com/athurnherr/LDEO_IX
cd LDEO_IX
# Apply Octave patches (see TECHNICAL.md)
```

Set the environment variable or update `ldeo_runner.py`:
```python
LDEO_PATCHED = '/path/to/TUNSIC26/04-LDEO-IX/patched'
LDEO_GEOMAG = '/path/to/TUNSIC26/04-LDEO-IX/geomag'
```

### 4. CTD Pre-processing (one-time)

Raw SBE `.hex` files must be converted to `.cnv` using Sea-Bird Data Processing
(free from seabird.com) or by processing with the GSW pipeline:

1. **DatCnv**: Hex → engineering units (P, T, C)
2. **Filter**: Low-pass 0.15 s (T, C), 0.50 s (O2)
3. **Align CTD**: Advance O2 +5 s, C/T +0.073 s
4. **Cell Thermal Mass**: α=0.03, 1/β=7.0
5. **Loop Edit**: Min velocity 0.25 m/s

The resulting `.cnv` files from Loop Edit are the input for `ctd_tool`.

---

## Quick Start

```bash
# Activate environment
source .venv/bin/activate

# Step 1: Process CTD data
python ladcp_tool/ctd_tool.py \
    --source-dir ./ProcessedCTD/07-LoopEdit \
    --output-dir ./ctd_output \
    --cruise-id MYCRUISE

# Step 2: Process LADCP data (uses CTD output for LDEO)
python ladcp_tool/ladcp_tool.py \
    --source-dir ./LADCP_raw \
    --ctd-dir ./ProcessedCTD/07-LoopEdit \
    --output-dir ./ladcp_output \
    --cruise-id MYCRUISE \
    --timeout 300
```

---

## ctd_tool

### Synopsis

```
ctd_tool -s <source-dir> -o <output-dir> [options]
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-s`, `--source-dir` | Yes | — | Directory with `.cnv` files |
| `-o`, `--output-dir` | Yes | — | Output root directory |
| `--bin-size` | No | `1.0` | Pressure bin width (dbar) |
| `--cruise-id` | No | `TUNSIC26` | Cruise identifier for output files |
| `--no-plots` | No | — | Skip plot generation |
| `--no-odv` | No | — | Skip ODV file generation |
| `--no-ldeo` | No | — | Skip LDEO-compatible ASCII output |

### Processing Steps

1. **Read CNV**: Parse Sea-Bird `.cnv` header and data columns
2. **Extract core variables**: Pressure (dbar), Temperature (°C ITS-90), Conductivity (S/m)
3. **Compute derived (GSW)**:
   - Practical Salinity (PSU) — `gsw.SP_from_C`
   - Absolute Salinity — `gsw.SA_from_SP`
   - Potential Temperature (°C) — `gsw.pt0_from_t`
   - Conservative Temperature — `gsw.CT_from_t`
   - Density σ₀ (kg/m³) — `gsw.sigma0`
   - In-situ Density — `gsw.rho`
   - Sound Speed (m/s) — `gsw.sound_speed`
   - Depth (m) — `gsw.z_from_p`
4. **Bin average**: Average to uniform pressure grid
5. **Output**: ASCII profiles, LDEO-compatible files, plots, ODV spreadsheets

### Validation

The GSW-derived variables have been validated against Sea-Bird Data Processing
output on cast 975 (501 levels, 0–497 m):

| Variable | RMSE vs SBE | Status |
|----------|-------------|--------|
| Salinity | 0.008 PSU | PASS |
| Density | 0.007 kg/m³ | PASS |
| Depth | 0.0004 m | PASS |

---

## ladcp_tool

### Synopsis

```
ladcp_tool -s <source-dir> -o <output-dir> [options]
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-s`, `--source-dir` | Yes | — | Directory with `MASTE*.000` / `SLAVE*.000` |
| `-o`, `--output-dir` | Yes | — | Output root directory |
| `--ctd-dir` | No | — | Directory with `.cnv` CTD files (enables full LDEO) |
| `--xmlcon` | No | auto-detect | Path to SBE XMLCON for CTD position info |
| `--skip-octave` | No | — | Skip Octave processing (quick-look only) |
| `--quick-look` | No | — | Generate diagnostic plots from raw LADCP data |
| `--timeout` | No | `600` | Timeout per cast for Octave (seconds) |
| `--cruise-id` | No | `TUNSIC26` | Cruise identifier |
| `--no-plots` | No | — | Skip plot generation |
| `--no-odv` | No | — | Skip ODV file generation |

### Processing Pipeline

When `--ctd-dir` is provided (full processing):

1. **File matching**: Match LADCP Master/Slave pairs with CTD casts by station ID
2. **CTD processing**: Convert `.cnv` to LDEO-compatible ASCII (elapsed time, P, T, S)
3. **Octave LDEO IX**: Execute the 17-step LDEO pipeline:
   - `loadrdi` — Read RDI binary, beam→Earth, initial QC
   - `loadctd` / `loadctdprof` — Load CTD time series and profile
   - `bestlag` — Time-synchronize ADCP and CTD clocks
   - `getdpth` — Compute depth from vertical velocity integration
   - `getbtrack` — Bottom tracking (RDI + acoustic backscatter)
   - `edit_data` — Quality control (error velocity, tilt, side-lobe)
   - `prepinv` — Form super-ensembles (depth binning)
   - `getinv` — Inverse solution (Visbeck 2002)
   - `calc_shear3` — Shear method solution
   - Results saved as ASCII velocity profiles
4. **Post-processing**: Read Octave output, generate plots and ODV files

When `--skip-octave` or `--quick-look`:
- Reads raw LADCP ensembles, extracts heading/pitch/roll/depth metadata
- No velocity inversion (diagnostic only)

### Cast Matching

The tool automatically matches LADCP and CTD files by station number, handling
prefix conventions (`S299` → `MASTE299`, `T840` → `MASTET840`, `809bis` → `MASTE809`).

---

## Output Description

Each tool creates the following subdirectories under `--output-dir`:

### ctd_tool output

```
output_dir/
├── results/                  # ASCII CTD profiles
│   └── <cast>_ctd_profile.txt
├── plots/                    # Publication-quality PNG plots
│   └── <cast>_ctd.png        # T-S diagram + T,S profiles + σ₀
├── odv/                      # ODV-compatible spreadsheets
│   ├── <cruise>_LADCP_collection.txt
│   └── <cruise>_<cast>_LADCP.txt
├── ldeo_ascii/               # LDEO-compatible CTD ASCII
│   ├── <cast>_ctd_timeseries.txt    # elapsed_sec P T S
│   └── <cast>_ctd_profile.txt      # binned P T S
└── <cruise>_LADCP_summary.txt       # Processing summary
```

### ladcp_tool output

```
output_dir/
├── results/                  # ASCII velocity profiles
│   └── <cast>_velocity_profile.txt  # Depth U V Error Speed
├── plots/                    # Velocity profile plots
│   ├── <cast>_velocity.png          # U, V, Speed
│   └── <cast>_combined.png          # Velocity + CTD
├── odv/                      # ODV spreadsheets (with velocity)
│   └── <cruise>_<cast>_LADCP.txt
├── work/                     # Octave working files (debug)
│   └── set_cast_params_<cast>.m
├── ctd_ascii/                # CTD ASCII for LDEO
│   └── <cast>_ctd_*.txt
└── <cruise>_LADCP_summary.txt
```

### Velocity Profile Format

```
# Depth(m)  U(m/s)  V(m/s)  Error(m/s)  Speed(m/s)
     5.0    0.1106  -0.1646      0.1074    0.1983
    10.0    0.1106  -0.1646      0.1068    0.1983
```

### ODV Spreadsheet Format

Tab-separated with standard ODV headers. Columns:
```
Pressure [dbar]  Depth [m]  Temperature [deg C]  Salinity [PSU]
SigmaTheta [kg/m3]  SoundSpeed [m/s]  U [m/s]  V [m/s]
U_Error [m/s]  PotTemp [deg C]
```

---

## ODV Compatibility

Open the collection file (`<cruise>_LADCP_collection.txt`) in Ocean Data View
(https://odv.awi.de) using **File → Open**. The collection references individual
station spreadsheets automatically.

Each spreadsheet includes:
- Standard ODV metadata (Cruise, Station, Type, Date, Lat, Lon, Bot. Depth)
- Variable declarations with units
- Column headers matching ODV naming conventions

---

## Troubleshooting

### "LDEO patched code not found"

Set the correct path in `ladcp_tool/processors/ldeo_runner.py`:
```python
LDEO_PATCHED = '/path/to/TUNSIC26/04-LDEO-IX/patched'
```

### Octave processing times out

Increase `--timeout`. Deep casts (>500 m) may require 600+ seconds on machines
with <4 GB RAM. Set `--skip-octave` for diagnostic-only mode.

### Matrix dimension errors (RAM)

Some deep casts fail with inversion matrix errors on machines with limited RAM.
Workarounds:
- Increase `p.avdz` (super-ensemble spacing, default 5 m) in set_cast_params
- Use a machine with 8+ GB RAM
- Process only shallow casts (<300 m)

### Missing CTD columns

The tool expects standard SBE column names: `prDM`, `t090C`, `c0S/m`.
If your CNV files use different names, verify they were processed through
DatCnv (not a raw hex file or earlier stage).

### Cast matching fails

The tool auto-matches by station number. If your files use a different convention,
you can:
- Rename files to match the expected pattern (e.g., `MASTE001.000`)
- Run `--skip-octave --quick-look` for diagnostic inspection only

---

## Examples

### Process all CTD casts from a cruise

```bash
python ladcp_tool/ctd_tool.py \
    -s /data/MYCRUISE/03-converted \
    -o /data/MYCRUISE/ctd_processed \
    --cruise-id MYCRUISE
```

### Process LADCP with CTD, generate all outputs

```bash
python ladcp_tool/ladcp_tool.py \
    -s /data/MYCRUISE/00-RAW-LADCP \
    --ctd-dir /data/MYCRUISE/03-converted \
    -o /data/MYCRUISE/ladcp_processed \
    --cruise-id MYCRUISE \
    --timeout 600
```

### Single cast with diagnostic plots only

```bash
# Copy one cast's files to a temp directory
mkdir /tmp/test_cast
cp MASTE299.000 SLAVE299.000 S299.cnv /tmp/test_cast/

python ladcp_tool/ladcp_tool.py \
    -s /tmp/test_cast \
    --ctd-dir /tmp/test_cast \
    -o /tmp/test_output \
    --quick-look \
    --cruise-id TEST
```

### CTD-only processing with 2 dbar bins

```bash
python ladcp_tool/ctd_tool.py \
    -s ./cnv_files \
    -o ./ctd_2dbar \
    --bin-size 2 \
    --cruise-id TEST
```

---

## References

- **Visbeck, M.** (2002). Deep velocity profiling using lowered acoustic Doppler
  current profilers: Bottom track and inverse solutions. *JAOT*, 19, 794–807.
- **Thurnherr, A.M.** (2024). LDEO LADCP Processing Software, Version IX_15.
  https://github.com/athurnherr/LDEO_IX
- **McDougall, T.J. & Barker, P.M.** (2011). Getting started with TEOS-10 and
  the Gibbs Seawater (GSW) Oceanographic Toolbox. SCOR/IAPSO WG127.
- **Sea-Bird Electronics** (2024). SBE Data Processing Manual.
  https://www.seabird.com/
