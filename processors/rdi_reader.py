# ladcp_tool/processors/rdi_reader.py
"""RDI Workhorse PD0 binary reader for LADCP data.

Reads raw .000 files and extracts velocity, heading, pitch, roll, 
temperature, ensemble time, and depth.
"""

import struct
from pathlib import Path
from datetime import datetime
import numpy as np

ENSEMBLE_SIZE = 664


class RDIFile:
    """Reader for RDI Workhorse PD0 binary files."""
    
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.name = self.filepath.name
        with open(self.filepath, 'rb') as f:
            self.data = f.read()
        self._nens = len(self.data) // ENSEMBLE_SIZE
        self._cache = {}
    
    def __len__(self):
        return self._nens
    
    def __iter__(self):
        for i in range(self._nens):
            ens = self.read(i)
            if ens is not None:
                yield ens
    
    def read_all(self):
        """Return all ensembles as structured arrays."""
        ensembles = []
        for ens in self:
            ensembles.append(ens)
        return _stack_ensembles(ensembles)
    
    def read(self, idx):
        """Read a single ensemble, return dict or None."""
        if idx in self._cache:
            return self._cache[idx]
        
        start = idx * ENSEMBLE_SIZE
        if start + ENSEMBLE_SIZE > len(self.data):
            return None
        
        hdr = struct.unpack_from('<11H', self.data, start)
        if hdr[0] != 0x7F7F:
            return None
        
        offsets = list(hdr[3:10])
        while offsets and offsets[-1] == 0:
            offsets.pop()
        
        if len(offsets) < 2:
            return None
        
        fl = self._parse_fl(start + offsets[0])
        if fl is None:
            return None
        
        ncells, nbeams = fl['n_cells'], fl['n_beams']
        if ncells == 0 or nbeams == 0:
            return None
        
        vl = self._parse_vl(start + offsets[1])
        vel = None
        corr, echo, pg = None, None, None
        
        for off in offsets[2:]:
            abs_off = start + off
            if abs_off + 2 > len(self.data):
                continue
            dt_id = struct.unpack_from('<H', self.data, abs_off)[0]
            
            if dt_id == 0x0100 and ncells > 0 and nbeams > 0:
                vel = self._read_velocity(abs_off + 2, ncells, nbeams)
            elif dt_id == 0x0200 and ncells > 0 and nbeams > 0:
                corr = self._read_uint8(abs_off + 2, ncells, nbeams)
            elif dt_id == 0x0300 and ncells > 0 and nbeams > 0:
                echo = self._read_uint8(abs_off + 2, ncells, nbeams)
            elif dt_id == 0x0400 and ncells > 0 and nbeams > 0:
                pg = self._read_uint8(abs_off + 2, ncells, nbeams)
        
        ens = {
            'ensemble': idx,
            'datetime': vl.get('datetime') if vl else None,
            'heading': vl.get('heading_deg', np.nan) if vl else np.nan,
            'pitch': vl.get('pitch_deg', np.nan) if vl else np.nan,
            'roll': vl.get('roll_deg', np.nan) if vl else np.nan,
            'temperature': vl.get('temperature_c', np.nan) if vl else np.nan,
            'salinity': vl.get('salinity_ppt', np.nan) if vl else np.nan,
            'depth_xdcr': vl.get('depth_transducer_m', np.nan) if vl else np.nan,
            'velocity': vel,
            'correlation': corr,
            'echo_intensity': echo,
            'percent_good': pg,
            'n_cells': ncells,
            'n_beams': nbeams,
            'cell_size': fl['cell_size_cm'],
            'blank': fl['blank_cm'],
            'bin1_dist': fl['bin1_dist_cm'],
            'fw_version': fl['fw_version'],
        }
        
        self._cache[idx] = ens
        return ens
    
    def _parse_fl(self, offset):
        """Parse Fixed Leader (0x0000 ID + 58 bytes body)."""
        if offset + 60 > len(self.data):
            return None
        
        dt_id = struct.unpack_from('<H', self.data, offset)[0]
        if dt_id != 0x0000:
            return None
        
        buf = self.data[offset+2:offset+60]
        
        def u16(off):
            return struct.unpack_from('<H', buf, off)[0]
        def u8(off):
            return buf[off]
        
        return {
            'fw_version': f'{u8(0)}.{u8(1)}',
            'n_beams': u8(6),
            'n_cells': u8(7),
            'pings_per_ens': u16(8),
            'cell_size_cm': u16(10),
            'blank_cm': u16(12),
            'bin1_dist_cm': u16(34),
            'coord_xform': u8(27),
            'heading_align_deg': u16(28) / 100.0,
            'heading_bias_deg': u16(30) / 100.0,
        }
    
    def _parse_vl(self, offset):
        """Parse Variable Leader (0x0080 ID + data)."""
        if offset + 67 > len(self.data):
            return None
        
        dt_id = struct.unpack_from('<H', self.data, offset)[0]
        if dt_id != 0x0080:
            return None
        
        buf = self.data[offset+2:offset+67]
        
        def u16(off):
            return struct.unpack_from('<H', buf, off)[0]
        def u8(off):
            return buf[off]
        
        year = u8(2) + (2000 if u8(2) < 100 else 1900)
        dt = None
        try:
            dt = datetime(year, u8(3), u8(4), u8(5), u8(6), u8(7), u8(8) * 10000)
        except (ValueError, OverflowError):
            pass
        
        heading = u16(16) / 100.0
        pitch = u16(18) / 100.0
        roll = u16(20) / 100.0
        if pitch > 180: pitch -= 360.0
        if roll > 180: roll -= 360.0
        
        return {
            'datetime': dt,
            'heading_deg': heading,
            'pitch_deg': pitch,
            'roll_deg': roll,
            'temperature_c': u16(24) / 100.0,
            'salinity_ppt': u16(22),
            'depth_transducer_m': u16(14) / 10.0,
            'speed_of_sound_mps': u16(12),
        }
    
    def _read_velocity(self, offset, ncells, nbeams):
        """Read beam velocity (int16, mm/s -> m/s)."""
        n = ncells * nbeams
        if offset + n * 2 > len(self.data):
            return None
        raw = struct.unpack_from('<' + 'h' * n, self.data, offset)
        arr = np.array(raw, dtype=np.float64).reshape(nbeams, ncells) / 1000.0
        arr = np.ma.masked_where(arr < -30.0, arr)
        return arr
    
    def _read_uint8(self, offset, ncells, nbeams):
        """Read correlation/echo/pct_good (uint8)."""
        n = ncells * nbeams
        if offset + n > len(self.data):
            return None
        raw = struct.unpack_from('<' + 'B' * n, self.data, offset)
        return np.array(raw, dtype=np.float64).reshape(nbeams, ncells)


def _stack_ensembles(ensembles):
    """Convert list of ensemble dicts to structured arrays."""
    ne = len(ensembles)
    if ne == 0:
        return None
    
    nc = ensembles[0]['n_cells']
    nb = ensembles[0]['n_beams']
    
    result = {
        'time': [],
        'heading': np.zeros(ne),
        'pitch': np.zeros(ne),
        'roll': np.zeros(ne),
        'temperature': np.zeros(ne),
        'depth_xdcr': np.zeros(ne),
        'velocity': np.ma.zeros((ne, nb, nc)),
        'n_cells': nc,
        'n_beams': nb,
        'cell_size_cm': ensembles[0]['cell_size'],
        'blank_cm': ensembles[0]['blank'],
        'bin1_dist_cm': ensembles[0]['bin1_dist'],
        'cell_depth': np.arange(nc) * ensembles[0]['cell_size'] / 100.0 
                      + ensembles[0]['bin1_dist'] / 100.0 
                      + ensembles[0]['cell_size'] / 200.0,
    }
    
    for i, e in enumerate(ensembles):
        result['time'].append(e['datetime'])
        result['heading'][i] = e['heading']
        result['pitch'][i] = e['pitch']
        result['roll'][i] = e['roll']
        result['temperature'][i] = e['temperature']
        result['depth_xdcr'][i] = e['depth_xdcr']
        if e['velocity'] is not None:
            result['velocity'][i] = e['velocity']
    
    return result
