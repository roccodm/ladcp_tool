function da=savearch(dr,d,p,ps,f,att)
% Stub for Octave - save dr results as simple ASCII
disp('  savearch: saving results to ASCII...');
fname = [f.res '_profile.txt'];
fid = fopen(fname, 'w');
fprintf(fid, '# LADCP velocity profile - cast %s\n', p.name);
fprintf(fid, '# Depth(m)  U(m/s)  V(m/s)  Error(m/s)\n');
for i = 1:length(dr.z)
    wval = 0;
    if isfield(dr, 'w')
        wval = dr.w(i);
    end
    fprintf(fid, '%8.1f  %8.4f  %8.4f  %8.4f\n', ...
        dr.z(i), dr.u(i), dr.v(i), dr.uerr(i));
end
fclose(fid);
fprintf('  Saved to %s (%d levels)\n', fname, length(dr.z));
da = struct();
