# Changelog

## [1.1.0] — 2026-06-28

### Added — CTD Processing (directives A1-A4)
- `isolate_downcast()`: extracts downcast only (median-filter max pressure +
  monotonicity filter), removing upcast hysteresis bias
- `check_pressure_monotonicity()`: standalone pressure inversion detection
- `--include-upcast` flag in ctd_tool (default: downcast only)
- `bin_profile_depth()`: bins to uniform depth grid (meters) via GSW z_from_p
- `--bin-axis` flag (pressure|depth, default: pressure) in ctd_tool
- `compute_ctd_qf()`: ODV/SeaDataNet quality flags for CTD variables
  (QF 1/3/4/9 with MEDITERRANEAN_RANGES module constant)
- ODV spreadsheets now include 5 QF columns (QF:Temperature, QF:Salinity,
  QF:SigmaTheta, QF:U, QF:V) — 15 columns total (was 10)

### Added — LADCP Processing (directives B1-B4)
- `savearch.m` rewritten: structured ASCII with 8 sections
  ([HEADER] [VELOCITY] [SHEAR] [UPDOWN] [CTD] [RANGE] [DIAGNOSTICS]
  [BOTTOM_TRACK]) — exports W (dr.wctd), shear, up/down, CTD (T/S/SS/N²),
  range, echo, bottom-track, warnings
- `dr.ctd_N2` interpolation added to process_cast.m STEP 17
- `read_ldeo_result()`: section-based parser with backward compatibility
  (old 4-column format still supported)
- `extract_processing_warnings()`: derives HIGH_ERROR and HEADING_OFFSET
  warnings from diagnostics/header
- `write_summary()`: MaxErr and Warnings columns added
- `compute_velocity_qf()`: quality flags for LADCP velocity
  (VELOCITY_QF_THRESHOLDS: uerr 0.05/0.10, speed 2.0/3.0)

### Fixed
- Pre-existing `bin_profile` threshold: `>3` (≥4 scans/bin) rejected all bins
  for already-binned CNV files; lowered to `>=1`
- Latent ODV bug `ladcp_tool.py:267`: ODV assembly reused last cast's
  `binned_ctd` for all casts; now stored per-cast in `result['binned_ctd']`
- Directives savearch bugs: dr.w→dr.wctd, nanmean→meannan, datestr(now)→
  sprintf(fix(clock)), parser warning extraction (content.startswith(' ')
  after strip → raw-line prefix detection)

### Validated
- 12/12 directives validation criteria pass on cast 975
- CTD: 497/996 scans (50%), 496 levels, no QF=4/9 in 5-490 dbar
- LADCP: U/V/uerr bit-for-bit identical to baseline, 8 savearch sections
- Upcast bias documented: RMSE 0.017 PSU (downcast vs full)

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
