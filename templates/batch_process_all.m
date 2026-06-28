% batch_process_all.m - Process all LADCP casts with CTD data
% Uses LDEO IX under Octave

disp('========================================');
disp('  BATCH LADCP PROCESSING - ALL CASTS');
disp('========================================');
disp(' ');

pkg load io;
pkg load statistics;

addpath('/home/rocco/LADCP/ext/LDEO_IX');
addpath('/home/rocco/LADCP/ext/LDEO_IX/geomag');

base_dir = '/home/rocco/LADCP/ldeo_work';
cast_ids = {'S299', 'S467', '638', '641', '806', '809bis', '975', '981', '987', 'T840', 'T843', 'T849', 'T909', 'T918', 'T921'};

n_casts = length(cast_ids);
results = cell(n_casts, 1);
errors = {};
success_count = 0;
fail_count = 0;

for c = 1:n_casts
    cast_id = cast_ids{c};
    cast_dir = fullfile(base_dir, ['cast_' cast_id]);
    
    fprintf('\n========================================\n');
    fprintf('[%d/%d] Processing cast %s\n', c, n_casts, cast_id);
    fprintf('========================================\n');
    
    try
        cd(cast_dir);
        clear f p d dr ds ps di de der att
        clear set_cast_params   % force reload from disk
        
        % Load per-cast configuration
        set_cast_params;
        
        % Run the full processing pipeline
        process_cast(cast_id, 1, 0);
        
        % Check if results were saved
        result_file = fullfile(cast_dir, ['result_' cast_id '_profile.txt']);
        if exist(result_file, 'file')
            fprintf('  *** CAST %s: SUCCESS ***\n', cast_id);
            results{c} = result_file;
            success_count = success_count + 1;
        else
            fprintf('  *** CAST %s: PARTIAL (no result file) ***\n', cast_id);
            errors{end+1} = sprintf('Cast %s: no result file', cast_id);
            fail_count = fail_count + 1;
        end
        
    catch e
        fprintf('  *** CAST %s: FAILED ***\n', cast_id);
        fprintf('  Error: %s\n', e.message);
        errors{end+1} = sprintf('Cast %s: %s', cast_id, e.message);
        fail_count = fail_count + 1;
    end
end

% Summary
disp(' ');
disp('========================================');
disp('  BATCH PROCESSING COMPLETE');
disp('========================================');
fprintf('  Total casts: %d\n', n_casts);
fprintf('  Successful:  %d\n', success_count);
fprintf('  Failed:      %d\n', fail_count);

if ~isempty(errors)
    disp(' ');
    disp('  Errors:');
    for i = 1:length(errors)
        fprintf('    - %s\n', errors{i});
    end
end

if success_count > 0
    disp(' ');
    disp('  Result files:');
    for i = 1:n_casts
        if ~isempty(results{i})
            fprintf('    %s\n', results{i});
        end
    end
end
