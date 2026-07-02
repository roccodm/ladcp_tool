# ladcp_tool

**Open-source LADCP & CTD processing pipeline for oceanographic cruises.**

Process lowered ADCP (Teledyne RDI Workhorse) and CTD (Sea-Bird SBE) data
from raw instrument files to velocity profiles, T-S diagrams, and
ODV-compatible spreadsheets — without commercial software dependencies.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Overview

`ladcp_tool` provides two independent command-line tools:

| Tool | Input | Output |
|------|-------|--------|
| `ctd_tool` | SBE `.cnv` files | CTD profiles (GSW-derived), T-S plots, ODV spreadsheets |
| `ladcp_tool` | RDI `.000` + CTD `.cnv` | Velocity profiles (LDEO IX inverse), velocity plots, ODV spreadsheets |

**Key features:**
- GSW TEOS-10 seawater properties validated against SBE Data Processing (RMSE < 0.01 PSU)
- Full LDEO IX processing pipeline (Visbeck 2002 shear + inverse method)
- Automatic Master/Slave LADCP synchronization (cross-correlation > 0.99)
- Dual-head complementary bin coverage (full water column)
- ODV-compatible spreadsheet output
- Publication-quality profile plots

## Quick Start

```bash
# 1. Install dependencies
sudo apt install -y build-essential gfortran python3.12-venv octave octave-statistics octave-io
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Install LDEO IX processing code
#    Download from https://github.com/athurnherr/LDEO_IX or use the included bundle
export LDEO_PATCHED=/path/to/LDEO_IX/patched
export LDEO_GEOMAG=/path/to/LDEO_IX/geomag

# 3. Process CTD
python ladcp_tool/ctd_tool.py -s ./cnv_files -o ./ctd_out --cruise-id MYCRUISE

# 4. Process LADCP
python ladcp_tool/ladcp_tool.py -s ./ladcp_raw --ctd-dir ./cnv_files -o ./ladcp_out
```

## Documentation

| Document | Audience | Content |
|----------|----------|---------|
| [USER_GUIDE.md](USER_GUIDE.md) | End users | Installation, CLI reference, output formats, ODV usage, troubleshooting |
| [TECHNICAL.md](TECHNICAL.md) | Developers | Architecture, algorithms, RDI binary format, GSW validation, Octave patches |
| [LIMITATIONS.md](LIMITATIONS.md) | All | Known issues, failure modes, workarounds, roadmap priorities |

## Validation

The GSW-derived CTD variables have been validated against Sea-Bird Data Processing
output on a 497 m deep Mediterranean cast (37,792 scans, 501 binned levels):

| Variable | RMSE vs SBE | Max Difference |
|----------|-------------|----------------|
| Salinity | **0.008 PSU** | 0.070 PSU |
| Density | **0.007 kg/m³** | 0.062 kg/m³ |
| Depth | **0.0004 m** | 0.001 m |

## Architecture

```
ladcp_tool/
├── ctd_tool.py             # CLI: CTD processing (GSW derived variables)
├── ladcp_tool.py           # CLI: LADCP processing (LDEO IX via Octave)
├── processors/
│   ├── ctd_processor.py    # CNV reader, GSW salinity/density, bin averaging
│   ├── rdi_reader.py       # RDI Workhorse PD0 binary format decoder
│   └── ldeo_runner.py      # Octave subprocess launcher for LDEO IX
├── outputs/
│   ├── odv_writer.py       # ODV-compatible spreadsheet format
│   ├── plotter.py          # Matplotlib profile/T-S plots
│   └── result_writer.py    # ASCII velocity and summary writers
├── utils/
│   └── cast_matcher.py     # LADCP/CTD file matching by station ID
├── USER_GUIDE.md           # User documentation
├── TECHNICAL.md            # Technical documentation
└── LIMITATIONS.md          # Known issues & roadmap
```

## Requirements

- **Python 3.12+** with numpy, scipy, matplotlib, gsw, cftime
- **GNU Octave 8.4+** with statistics and io packages
- **LDEO IX** processing code ([athurnherr/LDEO_IX](https://github.com/athurnherr/LDEO_IX))
- **CTD pre-processing**: `.cnv` files from Sea-Bird DatCnv (or equivalent)

## Instruments Supported

- **LADCP**: Teledyne RDI Workhorse (300 kHz), Master/Slave lowered configuration
- **CTD**: Sea-Bird SBE 9/11+/19/25 (via `.cnv` output)

## References

- Visbeck, M. (2002). "Deep velocity profiling using lowered ADCPs."
  *J. Atmos. Oceanic Technol.* 19, 794–807.
- Thurnherr, A.M. (2024). "LDEO LADCP Processing Software, Version IX_15."
- McDougall, T.J. & Barker, P.M. (2011). "TEOS-10 and GSW Oceanographic Toolbox."

## License

MIT — see [LICENSE](LICENSE).

This distribution includes third-party software under separate terms.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution and
license details of bundled components (LDEO IX, IGRF-13) and runtime
dependencies (GSW/TEOS-10, GEBCO).

### Note on LDEO IX

The LDEO LADCP Processing Software (Version IX_15) by M. Visbeck and
A.M. Thurnherr is bundled in `ldeo/patched/` with minor compatibility
patches. The upstream repository
([athurnherr/LDEO_IX](https://github.com/athurnherr/LDEO_IX)) does not
include an explicit license file; the software is distributed publicly by
the authors for scientific use. All original copyright notices are
retained. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.

## Contributing

Contributions are welcome. Please open an issue or pull request on GitHub.

## Citation

If you use this tool in a publication, please cite:

```
Rocco De Marco (2026).
ladcp_tool: Open-source LADCP & CTD processing pipeline.
https://github.com/<your-org>/ladcp_tool

Visbeck, M. (2002). Deep velocity profiling using lowered ADCPs.
J. Atmos. Oceanic Technol., 19, 794–807.
```
