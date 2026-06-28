# Changelog

## [1.0.0] — 2026-06-28

### Added
- `ctd_tool`: CLI for SBE `.cnv` to GSW-derived CTD profiles
  - CNV header and data parser
  - GSW TEOS-10 salinity, density, sound speed, potential temperature
  - Pressure bin averaging with configurable bin size
  - LDEO-compatible ASCII output (time series + binned profile)
  - ODV-compatible spreadsheet collection
  - Publication-quality T-S diagrams and vertical profile plots
- `ladcp_tool`: CLI for RDI LADCP processing via LDEO IX
  - RDI Workhorse PD0 binary reader (reverse-engineered WH300 format)
  - Automatic Master/Slave cast matching with CTD
  - Octave subprocess launcher for LDEO IX (17-step pipeline)
  - Velocity profile ASCII output with error estimates
  - ODV spreadsheets with combined CTD + LADCP data
- `processors/ctd_processor.py`: CNV reader, GSW derived variables, binning
- `processors/rdi_reader.py`: RDI WH300 binary format decoder
- `processors/ldeo_runner.py`: Octave LDEO IX integration
- Documentation: USER_GUIDE.md, TECHNICAL.md, LIMITATIONS.md, README.md

### Validated
- GSW salinity vs SBE: RMSE 0.008 PSU (cast 975, 501 levels, 497 m)
- GSW density vs SBE: RMSE 0.007 kg/m³
- GSW depth vs SBE: RMSE 0.0004 m
- 11 velocity profiles successfully processed from TUNSIC26 cruise data

### Known Limitations
- 6 deep casts fail on 2 GB RAM (matrix dimension errors)
- Requires GNU Octave + LDEO_IX for LADCP velocity inversion
- No `--resume` / incremental mode (see LIMITATIONS.md)
- Raw `.hex` CTD reader is experimental (pressure channel not validated)
