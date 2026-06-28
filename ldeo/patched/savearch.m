function da = savearch(dr, d, p, ps, f, att)
% SAVEARCH  Save LDEO IX results as structured ASCII.
%
% Output file: {f.res}_profile.txt
%
% Il file e' organizzato in sezioni delimitate da marcatori
% per facilitare il parsing in Python. Le sezioni sono:
%   [HEADER]       — metadati del cast e parametri di processing
%   [VELOCITY]     — profilo di velocita' principale (inversa)
%   [SHEAR]        — profilo dal metodo degli shear
%   [UPDOWN]       — profili separati up-only e down-only
%   [CTD]          — variabili CTD co-registrate sulla griglia LADCP
%   [RANGE]        — profilo di range acustico
%   [DIAGNOSTICS]  — statistiche di processing e quality metrics
%   [BOTTOM_TRACK] — dati di bottom tracking

disp('  savearch: saving structured results to ASCII...');
fname = [f.res '_profile.txt'];
fid = fopen(fname, 'w');

% ============================================================
% [HEADER]
% ============================================================
fprintf(fid, '[HEADER]\n');
fprintf(fid, '# Cast: %s\n', p.name);
if isfield(p,'lat')
  fprintf(fid, '# Latitude: %.4f\n', p.lat);
end
if isfield(p,'lon')
  fprintf(fid, '# Longitude: %.4f\n', p.lon);
end

fprintf(fid, '# MaxDepth_m: %.1f\n', abs(min(dr.z)));

if isfield(p,'zbottom') && isfinite(p.zbottom)
  fprintf(fid, '# BottomDepth_m: %.1f\n', p.zbottom);
end

fprintf(fid, '# NLevels: %d\n', length(dr.z));
fprintf(fid, '# VerticalResolution_m: %.1f\n', ...
    medianan(abs(diff(dr.z))));

if isfield(p,'avdz')
  fprintf(fid, '# SuperEnsemble_dz_m: %.1f\n', p.avdz);
end
if isfield(ps,'shear')
  fprintf(fid, '# ShearMethod: %d\n', ps.shear);
end
if isfield(p,'up_dn_comp_off')
  fprintf(fid, '# HeadingOffset_deg: %.2f\n', p.up_dn_comp_off);
end
if isfield(p,'ctdmaxlag')
  fprintf(fid, '# CTDMaxLag: %d\n', p.ctdmaxlag);
end

fprintf(fid, '# ProcessingDate: %s\n', ...
    sprintf('%04d-%02d-%02d %02d:%02d:%02d', fix(clock)));
fprintf(fid, '\n');

% ============================================================
% [VELOCITY]  — profilo inversa (soluzione principale)
% ============================================================
fprintf(fid, '[VELOCITY]\n');
fprintf(fid, '# Depth_m  U_m/s  V_m/s  Uerr_m/s');

has_w = isfield(dr,'wctd') && length(dr.wctd) == length(dr.z);
if has_w
  fprintf(fid, '  W_m/s');
end
fprintf(fid, '\n');

for i = 1:length(dr.z)
  fprintf(fid, '%8.1f  %9.4f  %9.4f  %9.4f', ...
      dr.z(i), dr.u(i), dr.v(i), dr.uerr(i));
  if has_w
    fprintf(fid, '  %9.4f', dr.wctd(i));
  end
  fprintf(fid, '\n');
end
fprintf(fid, '\n');

% ============================================================
% [SHEAR]  — profilo dal metodo shear
% ============================================================
has_shear = isfield(dr,'u_shear_method') && ...
            length(dr.u_shear_method) == length(dr.z);
if has_shear
  fprintf(fid, '[SHEAR]\n');
  fprintf(fid, '# Depth_m  U_shear_m/s  V_shear_m/s\n');
  for i = 1:length(dr.z)
    fprintf(fid, '%8.1f  %9.4f  %9.4f\n', ...
        dr.z(i), dr.u_shear_method(i), dr.v_shear_method(i));
  end
  fprintf(fid, '\n');
end

% ============================================================
% [UPDOWN]  — profili separati per strumento
% ============================================================
has_updn = isfield(dr,'u_do') && isfield(dr,'u_up') && ...
           length(dr.u_do) == length(dr.z);
if has_updn
  fprintf(fid, '[UPDOWN]\n');
  fprintf(fid, '# Depth_m  U_down_m/s  V_down_m/s  U_up_m/s  V_up_m/s\n');
  for i = 1:length(dr.z)
    fprintf(fid, '%8.1f  %9.4f  %9.4f  %9.4f  %9.4f\n', ...
        dr.z(i), dr.u_do(i), dr.v_do(i), dr.u_up(i), dr.v_up(i));
  end
  fprintf(fid, '\n');
end

% ============================================================
% [CTD]  — variabili CTD sulla griglia LADCP
% ============================================================
has_ctd = isfield(dr,'ctd_t') && length(dr.ctd_t) == length(dr.z);
if has_ctd
  fprintf(fid, '[CTD]\n');
  fprintf(fid, '# Depth_m  Pressure_dbar  Temp_C  Sal_PSU');
  has_ss = isfield(dr,'ctd_ss') && length(dr.ctd_ss) == length(dr.z);
  has_n2 = isfield(dr,'ctd_N2') && length(dr.ctd_N2) == length(dr.z);
  if has_ss; fprintf(fid, '  SoundSpeed_m/s'); end
  if has_n2; fprintf(fid, '  N2_1/s2'); end
  fprintf(fid, '\n');

  for i = 1:length(dr.z)
    fprintf(fid, '%8.1f  %8.1f  %8.3f  %8.3f', ...
        dr.z(i), dr.p(i), dr.ctd_t(i), dr.ctd_s(i));
    if has_ss; fprintf(fid, '  %8.2f', dr.ctd_ss(i)); end
    if has_n2; fprintf(fid, '  %12.6e', dr.ctd_N2(i)); end
    fprintf(fid, '\n');
  end
  fprintf(fid, '\n');
end

% ============================================================
% [RANGE]  — profilo di range acustico
% ============================================================
has_range = isfield(dr,'range') && length(dr.range) == length(dr.z);
if has_range
  fprintf(fid, '[RANGE]\n');
  fprintf(fid, '# Depth_m  Range_total_m  Range_down_m  Range_up_m\n');
  has_rd = isfield(dr,'range_do') && length(dr.range_do) == length(dr.z);
  has_ru = isfield(dr,'range_up') && length(dr.range_up) == length(dr.z);
  for i = 1:length(dr.z)
    fprintf(fid, '%8.1f  %8.1f', dr.z(i), dr.range(i));
    if has_rd; fprintf(fid, '  %8.1f', dr.range_do(i)); end
    if has_ru; fprintf(fid, '  %8.1f', dr.range_up(i)); end
    fprintf(fid, '\n');
  end
  fprintf(fid, '\n');
end

% ============================================================
% [DIAGNOSTICS]
% ============================================================
fprintf(fid, '[DIAGNOSTICS]\n');

fprintf(fid, '# MeanError_m/s: %.4f\n', meannan(dr.uerr));
fprintf(fid, '# MaxError_m/s: %.4f\n', maxnan(dr.uerr));

if isfield(dr,'ensemble_vel_err')
  fprintf(fid, '# MeanEnsembleErr_m/s: %.4f\n', ...
      meannan(dr.ensemble_vel_err));
end

if isfield(dr,'ts') && length(dr.ts) == length(dr.z)
  fprintf(fid, '# MeanEchoAmplitude_dB: %.1f\n', meannan(dr.ts));
end

if isfield(p,'warn') && ~isempty(p.warn)
  fprintf(fid, '# Warnings:\n');
  for i = 1:size(p.warn, 1)
    wline = strtrim(p.warn(i, :));
    if ~isempty(wline)
      fprintf(fid, '#   %s\n', wline);
    end
  end
end
if isfield(p,'warnp') && ~isempty(p.warnp)
  if ~isfield(p,'warn') || isempty(p.warn)
    fprintf(fid, '# Warnings:\n');
  end
  for i = 1:size(p.warnp, 1)
    wline = strtrim(p.warnp(i, :));
    if ~isempty(wline)
      fprintf(fid, '#   %s\n', wline);
    end
  end
end
fprintf(fid, '\n');

% ============================================================
% [BOTTOM_TRACK]
% ============================================================
if isfield(p,'zbottom') && isfinite(p.zbottom)
  fprintf(fid, '[BOTTOM_TRACK]\n');
  fprintf(fid, '# BottomDepth_m: %.1f\n', p.zbottom);
  if isfield(dr,'zbot')
    fprintf(fid, '# BT_Depth_m: %.1f\n', dr.zbot);
  end
  if isfield(dr,'ubot') && isfield(dr,'vbot')
    fprintf(fid, '# BT_U_m/s: %.4f\n', dr.ubot);
    fprintf(fid, '# BT_V_m/s: %.4f\n', dr.vbot);
  end
  fprintf(fid, '\n');
end

fclose(fid);
fprintf('  Saved to %s (%d levels, %d sections)\n', fname, length(dr.z), ...
    1 + has_shear + has_updn + has_ctd + has_range + 1);
da = struct();
