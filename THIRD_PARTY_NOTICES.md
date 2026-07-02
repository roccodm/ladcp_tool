# Third-Party Software Notices

This distribution includes or makes use of third-party software components.
The licenses and attribution requirements for each are described below.

---

## 1. LDEO LADCP Processing Software (Version IX_15)

- **Directory**: `ldeo/patched/`, `ldeo/original/`
- **Files**: 66 `.m` files (MATLAB/Octave)
- **Authors**: Martin Visbeck (LDEO, 1998–2003), A.M. Thurnherr (LDEO, 2004–2024)
- **Source**: https://github.com/athurnherr/LDEO_IX
- **License**: None explicitly stated. The software is distributed publicly
  by the authors for scientific use. Copyright notices are retained in
  each file header (e.g. `(c) 2004 A.M. Thurnherr`, `Martin Visbeck LDEO`).

### Attribution

> Visbeck, M. (2002). "Deep velocity profiling using lowered ADCPs:
> Frame noise reduction and navigation corrections."
> *Journal of Atmospheric and Oceanic Technology*, 19(5), 794–807.
> https://doi.org/10.1175/1520-0426(2002)019<0794:DVPULR>2.0.CO;2
>
> Thurnherr, A.M. (2024). "LDEO LADCP Processing Software, Version IX_15."
> https://github.com/athurnherr/LDEO_IX

### Modifications

The `ldeo/patched/` directory contains a patched copy of LDEO IX with
the following modifications applied by the TUNSIC26 LADCP Tool Contributors:

- `loadctd.m`: Fixed wctd outlier detection (center on mean, not on zero)
  and added `pressure_noise` parameter for depth-as-pressure fallback
- `process_cast.m`: Compatibility patches for GNU Octave 8.4+
- `magdev.m`: Updated IGRF coefficients to IGRF-13 (2019 release)

All original copyright notices are preserved. The patched code remains
attributable to the original authors.

---

## 2. IGRF-13 Geomagnetic Model Coefficients

- **Directory**: `ldeo/geomag/`
- **Files**: `IGRF13coeffs.txt`, `IGRF13coeffs.mat`, `IGRF13coeffs.xlsx`
- **Source**: https://www.ngdc.noaa.gov/IAGA/vmod/igrf.html
- **Maintainer**: IAGA (International Association of Geomagnetism and Aeronomy),
  hosted by NOAA/NCEI
- **License**: Public domain.

> "The software code is in the public domain and not licensed or under
> copyright. The information and software may be used freely by the public."
> — NOAA/NCEI, https://www.ngdc.noaa.gov/IAGA/vmod/geomag70_license.html

### Citation

> Alken, P., Thébault, E., Beggan, C.D. et al. (2021).
> "International Geomagnetic Reference Field: the thirteenth generation."
> *Earth, Planets and Space*, 73, 49.
> https://doi.org/10.1186/s40623-020-01288-x

---

## 3. MathWorks Function Snippets

A small number of LDEO IX `.m` files contain legacy MATLAB function snippets
dating from MATLAB V1/V2 (1985–1986), authored by J.N. Little and bearing
`Copyright (c) 1985, 1986 by the MathWorks, Inc.` These snippets
(`spline`, `detrend`, etc.) predate MATLAB's modern licensing and have been
widely redistributed in academic Octave-compatible code for decades. They are
retained here unmodified as part of the LDEO IX distribution.

---

## 4. GSW (TEOS-10) Oceanographic Toolbox

- **Used via**: Python `gsw` package (pip dependency, not bundled)
- **Authors**: McDougall & Barker (2011)
- **License**: GNU General Public License v3 (GPL-3.0)
- **Source**: https://github.com/TEOS-10/GSW-Python

The `gsw` Python package is a runtime dependency declared in
`requirements.txt` and is not included in this repository. Users install it
separately via pip. The GPL-3.0 license of `gsw` applies to that package
only, not to this repository's MIT-licensed code.

### Citation

> McDougall, T.J. & Barker, P.M. (2011).
> "Getting started with TEOS-10 and the Gibbs Seawater (GSW) Oceanographic
> Toolbox." SCOR/IAPSO WG127, 28 pp.
> https://www.teos-10.org/

---

## 5. GEBCO 2026 Bathymetric Grid

- **Used via**: Subset GeoTIFF downloaded by the user at runtime
- **Source**: https://download.gebco.net/
- **License**: Public domain (GEBCO is placed in the public domain)

GEBCO grid data is not bundled in this repository. Users download regional
subsets directly from the GEBCO download service.

### Citation

> GEBCO Bathymetric Compilation Group 2026 (2026).
> "The GEBCO_2026 Grid — a continuous terrain model for oceans and land
> at 15 arc-second intervals."
> https://doi.org/10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa

---

## Summary

| Component | License | Bundled? | Compatible with MIT? |
|-----------|---------|----------|----------------------|
| ladcp_tool (this repo) | MIT | — | — |
| LDEO IX (`.m` files) | No explicit license (academic public use) | Yes | Yes (publicly distributed, attribution retained) |
| IGRF-13 coefficients | Public domain | Yes | Yes |
| MathWorks snippets | MathWorks (legacy, pre-V5) | Yes (in LDEO) | Yes (historical academic redistribution) |
| GSW (TEOS-10) | GPL-3.0 | No (pip dependency) | N/A (separate work, dynamic dependency) |
| GEBCO 2026 grid | Public domain | No (user download) | Yes |
