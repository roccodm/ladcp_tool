# LADCP Tool Suite — Limitations & Known Issues

**Version 1.0.0** — June 2026

This document describes known limitations, failure modes, and areas for improvement.
Each section covers the problem, its practical impact, current workarounds, and
suggested resolution priority.

---

## 1. External Dependencies

### Octave + LDEO_IX required for LADCP processing

The core velocity inversion (LDEO IX) runs inside GNU Octave as a subprocess.
There is no pure-Python fallback for the inverse method or shear method.

**Impact**: On a system without Octave installed, `ladcp_tool` produces only
CTD profiles and raw LADCP quick-look data — no velocity profiles. On a cruise
ship where software installation may be restricted, this is a showstopper.

**Workaround**: Pre-install Octave and the LDEO_IX patched code before the
campaign. Bundle the TUNSIC26 tarball which includes everything.

**Priority**: Medium. The Visbeck (2002) inverse method is mathematically
well-defined and could be re-implemented in Python using `scipy.sparse.linalg`.
A pure-Python port would eliminate the Octave dependency entirely.

---

## 2. RAM Constraints on Deep Casts

### Matrix dimension errors below 2 GB RAM

The LDEO inversion constructs a design matrix whose size grows with
the number of depth levels × the number of super-ensemble constraints.
Deep casts (>500 m, >100 levels) may exceed available memory on small machines.

On a 2 GB VM, 6 out of 16 TUNSIC26 casts failed with nonconformant matrix errors
(casts: 299, 987, T849, T918, T921, T846).

**Impact**: Deep-cast processing requires ≥4 GB RAM. Shallow casts (<300 m)
always succeed. On a cruise laptop with limited RAM, deep stations will fail
silently.

**Workaround**: Increase `p.avdz` (super-ensemble spacing) in the per-cast
`set_cast_params.m` to reduce matrix dimensions. Or process on a larger
machine post-campaign.

**Priority**: Medium. A graceful degradation path (e.g., automatic downsampling
when memory is low) would make the tool more robust.

---

## 3. Cast Matching

### Naming convention assumption

`cast_matcher.py` assumes LADCP files follow the pattern `MASTE<ID>.000` /
`SLAVE<ID>.000` and CTD files contain the same `<ID>` in their name (with
optional `S`/`T` prefix or `TUNSIC` suffix). Arbitrary naming conventions
will not match.

**Impact**: On a cruise where files are named `cast001_down.000` or
`stn_042.hex`, the tool will report "LADCP without CTD" and skip processing.

**Workaround**: Rename files before processing, or modify `cast_matcher.py`
with cruise-specific regex patterns.

**Priority**: Low. Adding a YAML/JSON config file for manual station-to-file
mapping would solve this generically.

---

## 4. Error Handling & Diagnostics

### Silent failures

When Octave processing fails:
- The tool prints "FAILED" but the Octave stdout/stderr is truncated to the last
  500 characters
- There is no structured error classification (memory vs syntax vs data quality)
- No retry logic with adjusted parameters

When a CTD cast fails (e.g., cast 641 with a boolean index mismatch from
one extra bad-value scan), the tool skips it without explaining which row
caused the error.

**Impact**: During a campaign with 3–4 casts per day, an operator may not have
time to debug failures. Accumulated unprocessed casts reduce scientific return.

**Workaround**: Run the failing cast manually with `--verbose` (not yet
implemented) or re-run with the standalone Octave script in the `work/` directory.

**Priority**: Medium. Streaming Octave output in real-time and classifying
errors by type would significantly improve the operator experience.

---

## 5. Incremental Scalability

### No resume capability

Every invocation of `ctd_tool` or `ladcp_tool` processes **all** files in the
source directory, regardless of whether they were already processed. There is
no `--resume` flag, no `--cast <id>` selector, and no state file tracking
completed casts.

**Impact**: During a cruise adding 2–3 casts per day, by day 15 the tool
reprocesses 45 casts every run (~10 minutes). This discourages frequent use
and pushes processing to post-cruise, losing the real-time quality-control
benefit.

**Workaround**: Manually move processed files to a subdirectory, or run the
Octave processing directly for individual casts using the generated
`set_cast_params_<id>.m` scripts.

**Priority**: High. Three features would solve this:
1. `--cast <id>` to process a single station
2. `--resume` to skip casts with existing output files
3. A JSON state file tracking input file hashes → output file paths

---

## 6. Reproducibility

### No output versioning

Results are written to fixed filenames (e.g., `result_S299_profile.txt`).
Re-running the tool with different parameters **overwrites** previous results.
There is no timestamp, parameter hash, or version suffix in the output
filenames.

**Impact**: If you experiment with different bin sizes or quality-control
thresholds, you lose the previous results. Comparing two processing runs
requires manual file management.

**Workaround**: Use different `--output-dir` values for each run, or rename
files manually after processing.

**Priority**: Medium. Adding a `--tag` parameter that suffixes output filenames
(`result_S299_v2_profile.txt`) would provide basic versioning.

---

## 7. CTD Raw Hex Reader

### Pressure channel not validated

The SBE hex parser (`sbe_processor.py`, experimental) correctly decodes
temperature and conductivity from raw `.hex` files (T validated to 0.01°C,
C validated to 0.003 S/m). However, the Digiquartz pressure channel conversion
is **not yet functional** — the raw period-to-pressure formula produces values
off by orders of magnitude.

**Impact**: The tool suite cannot process raw `.hex` files directly. Users must
pre-process CTD data through Sea-Bird Data Processing (DatCnv step) to obtain
`.cnv` files. This introduces a commercial software dependency for the initial
conversion step.

**Workaround**: Run DatCnv from SBEDataProcessing (free, registration required)
before using the tool. The subsequent processing steps (Filter, Align, CellTM,
LoopEdit, Derive, BinAvg) are not needed — only DatCnv is required to produce
`.cnv` files with engineering units.

**Priority**: Medium. The SBE Digiquartz formula is well-documented. The issue
is likely a unit conversion (period in µs vs ms vs raw counts) that can be
resolved by studying the Sea-Bird Data Processing manual §Pressure Sensors.

---

## 8. Platform Support

### Linux-only tested

The tool suite has been tested on **Ubuntu 24.04 (amd64)** with Python 3.12 and
GNU Octave 8.4. No testing has been performed on:
- macOS (Octave via Homebrew may have different path handling)
- Windows (subprocess model differs; Octave on Windows uses different path
  separators)
- ARM architectures (Raspberry Pi, Apple Silicon — Octave package availability
  varies)

**Impact**: The tool may not work out-of-the-box on non-Linux platforms.
Cruise ship acquisition PCs often run Windows.

**Workaround**: Use a Linux VM or Docker container on Windows/macOS. The
`TUNSIC26.tar.gz` package includes everything needed for a containerized
deployment.

**Priority**: Low. Containerization (Dockerfile with Ubuntu + Octave + Python
venv) would make the tool platform-independent.

---

## 9. ODV Output Completeness

### No quality flags in ODV files

The ODV spreadsheets include velocity and CTD variables but lack ODV-standard
quality flags (QF columns). ODV uses integer flags (0=unknown, 1=good, 2=probably
good, 3=probably bad, 4=bad, ...) to enable filtering.

**Impact**: ODV cannot automatically color-code or filter data points by quality.
Users must manually inspect profiles.

**Priority**: Low. Adding QF columns with the LDEO error velocity as a
threshold-based quality flag (e.g., flag=1 if uerr < 0.1 m/s) would be
straightforward.

---

## 10. Missing Pre-Flight Checks

### No input data validation before processing

The tool does not verify:
- File size sanity (e.g., a 100-byte `.000` file is corrupt but not detected)
- Instrument configuration consistency across casts (different cell sizes,
  blank distances would produce incorrect profiles)
- Clock drift between Master and Slave ADCPs (reported as a warning in
  Octave but not surfaced to the Python tool)
- CTD pressure range vs LADCP depth range consistency

**Impact**: Corrupt or misconfigured data produces garbage profiles with no
warning. On a cruise, a miswired sensor or wrong deployment script could go
undetected for multiple casts.

**Priority**: Medium. Adding a `--validate` mode that checks file integrity,
configuration consistency, and clock offsets would provide a valuable
pre-processing safety net.

---

## Summary

| # | Limitation | Impact | Priority |
|---|-----------|--------|----------|
| 1 | Octave required, no Python fallback | Cannot process LADCP without Octave | Medium |
| 2 | Deep casts need >2 GB RAM | 6/16 TUNSIC26 casts failed on 2 GB | Medium |
| 3 | Rigid file naming convention | Fails on non-standard names | Low |
| 4 | Silent failures, truncated logs | Hard to debug during campaign | Medium |
| 5 | No `--resume` / `--cast` selector | Reprocesses all casts every run | **High** |
| 6 | Results overwritten without versioning | Cannot compare processing runs | Medium |
| 7 | Raw hex pressure reader broken | Requires commercial DatCnv step | Medium |
| 8 | Linux-only tested | May not work on Windows/macOS | Low |
| 9 | No quality flags in ODV output | Manual QC required in ODV | Low |
| 10 | No pre-flight data validation | Corrupt data produces garbage silently | Medium |

*Priority definitions:* **High** = essential for campaign use; **Medium** =
important for robustness; **Low** = nice-to-have, limited user impact.
