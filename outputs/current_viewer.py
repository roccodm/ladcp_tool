# ladcp_tool/outputs/current_viewer.py
"""Modulo di visualizzazione 3D delle correnti oceaniche LADCP.

Produce scene 3D interattive (Plotly) con:
  - superficie batimetrica GEBCO
  - coni vettoriali colorati per velocita' per strato di profondita'
  - colonne verticali alle stazioni
  - piano semitrasparente della superficie del mare
  - dropdown per selezione strato attivo
  - mappe 2D per strato (Plotly Mapbox)
  - sezioni verticali lungo la rotta (heatmap + stazioni)

Output: file HTML autonomo apribile offline nel browser.
"""

import numpy as np
from pathlib import Path
from datetime import datetime


# ---------- Costanti di stile ----------

COLORSCALE_SPEED = [
    [0.0,  '#2a78d6'],
    [0.25, '#1baf7a'],
    [0.5,  '#eda100'],
    [0.75, '#eb6834'],
    [1.0,  '#e34948'],
]

COLORSCALE_BATHY = [
    [0.0,  '#04342C'],
    [0.3,  '#0F6E56'],
    [0.6,  '#5DCAA5'],
    [0.85, '#E1F5EE'],
    [1.0,  '#F1EFE8'],
]

STATION_LINE_COLOR = 'rgba(100, 100, 100, 0.4)'
STATION_LABEL_SIZE = 10


# ---------- 1. Lettura dati ----------

def load_station_metadata(odv_dir, cruise_id='TUNSIC26'):
    """Legge lat, lon, bottom_depth e datetime dagli header ODV.

    Scansiona tutti i file *_LADCP.txt nella directory ODV e ne
    estrae i metadati dalla riga di dati (prima riga dopo gli header
    // e le dichiarazioni di variabile).

    Args:
        odv_dir: path alla directory odv/ prodotta da ladcp_tool
        cruise_id: identificativo crociera (per filtrare i file)

    Returns:
        dict {station_id: {lat, lon, bottom_depth, datetime}}
    """
    stations = {}
    odv_path = Path(odv_dir)

    for f in sorted(odv_path.glob(f'{cruise_id}_*_LADCP.txt')):
        station_id = f.stem.replace(f'{cruise_id}_', '').replace('_LADCP', '')

        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('//') or line.startswith('<'):
                    continue
                if line.startswith('Cruise'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    try:
                        stations[station_id] = {
                            'lon': float(parts[4]),
                            'lat': float(parts[5]),
                            'bottom_depth': float(parts[6]),
                            'datetime': datetime.strptime(
                                parts[3][:19], '%Y-%m-%dT%H:%M:%S'),
                        }
                    except (ValueError, IndexError):
                        pass
                break

    return stations


def load_velocity_profile(profile_path):
    """Legge un singolo profilo di velocita' ASCII.

    Formato atteso (da result_writer.py):
        # Depth(m)  U(m/s)  V(m/s)  Error(m/s)  Speed(m/s)

    Returns:
        dict {depth, u, v, uerr, speed} arrays numpy, o None.
    """
    data = []
    with open(profile_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                vals = [float(x) for x in line.split()]
                if len(vals) >= 5:
                    data.append(vals)
            except ValueError:
                continue

    if not data:
        return None

    arr = np.array(data)
    return {
        'depth': arr[:, 0],
        'u': arr[:, 1],
        'v': arr[:, 2],
        'uerr': arr[:, 3],
        'speed': arr[:, 4],
    }


def load_all_stations(results_dir, odv_dir, cruise_id='TUNSIC26'):
    """Carica tutti i dati di stazione: metadati + profili di velocita'.

    Args:
        results_dir: path a results/ (contiene *_velocity_profile.txt)
        odv_dir: path a odv/ (contiene *_LADCP.txt con header)
        cruise_id: identificativo crociera

    Returns:
        list of dict, ciascuno con:
            station, lat, lon, bottom_depth, datetime,
            depth[], u[], v[], uerr[], speed[]
    """
    meta = load_station_metadata(odv_dir, cruise_id)
    res_path = Path(results_dir)
    stations = []

    for station_id, info in meta.items():
        vp_file = res_path / f'{station_id}_velocity_profile.txt'
        if not vp_file.exists():
            print(f'  WARNING: velocity profile not found for {station_id}')
            continue

        profile = load_velocity_profile(vp_file)
        if profile is None:
            print(f'  WARNING: empty velocity profile for {station_id}')
            continue

        stations.append({
            'station': station_id,
            **info,
            **profile,
        })

    print(f'  Loaded {len(stations)} stations with velocity data')
    return stations


# ---------- 2. Estrazione slice di profondita' ----------

def extract_depth_slices(stations, target_depths=None):
    """Estrae le velocita' per ciascuno strato di profondita'.

    Per ogni profondita' target e ogni stazione, interpola linearmente
    U e V dal profilo verticale. Stazioni la cui profondita' massima
    e' inferiore al target vengono escluse da quello strato.

    Args:
        stations: lista da load_all_stations()
        target_depths: lista di profondita' in metri (default:
                       [5, 10, 25, 50, 100, 150, 200, 300, 400, 500])

    Returns:
        dict {depth_m: list of dict} dove ogni dict contiene:
            station, lat, lon, u, v, speed, uerr, direction_deg
    """
    if target_depths is None:
        target_depths = [5, 10, 25, 50, 100, 150, 200, 300, 400, 500]

    slices = {}

    for target_z in target_depths:
        layer = []

        for stn in stations:
            z = stn['depth']
            u = stn['u']
            v = stn['v']
            uerr = stn['uerr']

            if target_z > np.nanmax(z):
                continue

            u_interp = float(np.interp(target_z, z, u))
            v_interp = float(np.interp(target_z, z, v))
            err_interp = float(np.interp(target_z, z, uerr))

            speed = float(np.sqrt(u_interp**2 + v_interp**2))
            direction = float(np.degrees(
                np.arctan2(u_interp, v_interp)) % 360)

            layer.append({
                'station': stn['station'],
                'lat': stn['lat'],
                'lon': stn['lon'],
                'u': u_interp,
                'v': v_interp,
                'speed': speed,
                'uerr': err_interp,
                'direction_deg': direction,
            })

        slices[target_z] = layer

    return slices


# ---------- 3. Costruzione della scena 3D ----------

def build_bathymetry_surface(bathy, opacity=0.85):
    """Costruisce la superficie batimetrica come go.Surface."""
    lon_mesh, lat_mesh = np.meshgrid(bathy['lon_grid'],
                                      bathy['lat_grid'])

    return go.Surface(
        x=lon_mesh,
        y=lat_mesh,
        z=bathy['elevation'],
        colorscale=COLORSCALE_BATHY,
        opacity=opacity,
        showscale=True,
        colorbar=dict(
            title=dict(text='Profondita (m)', side='right'),
            x=1.02,
            len=0.4,
            y=0.2,
            tickprefix='-',
        ),
        name='Fondale GEBCO',
        hovertemplate=(
            'Lon: %{x:.3f}<br>'
            'Lat: %{y:.3f}<br>'
            'Profondita: %{z:.0f} m<br>'
            '<extra>Fondale</extra>'
        ),
        lighting=dict(
            ambient=0.6,
            diffuse=0.5,
            specular=0.1,
            roughness=0.8,
        ),
        contours=dict(
            z=dict(
                show=True,
                usecolormap=False,
                highlightcolor='rgba(255,255,255,0.3)',
                project=dict(z=False),
                width=1,
                start=-600,
                end=0,
                size=50,
            )
        ),
    )


def _compute_cone_size_factor(stations):
    """Calcola CONE_SIZE_FACTOR dinamico basato sull'estensione spaziale.

    Il fattore originale (0.015) era calibrato per gradi ma su range
    ampi produce coni invisibili. Lo scalo all'estensione lon/lat delle
    stazioni, mantenendo i coni leggibili.
    """
    lons = [s['lon'] for s in stations]
    lats = [s['lat'] for s in stations]
    extent = max(max(lons) - min(lons), max(lats) - min(lats))
    if extent <= 0:
        return 0.015
    # Coni ~3% dell'estensione spaziale per 1 m/s
    return 0.03 * extent


def interpolate_velocity_field(layer, grid_n=12, method='linear'):
    """Interpola il campo di velocita' (U, V) su una griglia regolare.

    Partendo dai punti di stazione (sparsi), produce una griglia
    regolare grid_n x grid_n di frecce interpolando U e V separatamente.
    Questo permette di visualizzare un campo di flusso continuo invece
    di poche frecce isolate alle sole posizioni delle stazioni.

    I punti della griglia che cadono fuori dal convex hull delle
    stazioni (non interpolabili con metodo 'linear') vengono scartati.

    Args:
        layer: list of dict da extract_depth_slices() per uno strato
               (ogni dict ha: lon, lat, u, v, speed, uerr, station)
        grid_n: numero di celle per lato della griglia (default 12,
                produce fino a 144 punti)
        method: 'linear' (default, raccomandato) o 'nearest'

    Returns:
        list of dict nello stesso formato di layer, ma con i punti
        interpolati sulla griglia. I punti non interpolabili (NaN)
        vengono esclusi. I punti corrispondenti alle stazioni reali
        mantengono il nome della stazione; i punti interpolati hanno
        station='grid'.
    """
    from scipy.interpolate import griddata

    if len(layer) < 3:
        return list(layer)

    pts = np.array([[p['lon'], p['lat']] for p in layer])
    u_vals = np.array([p['u'] for p in layer])
    v_vals = np.array([p['v'] for p in layer])
    err_vals = np.array([p['uerr'] for p in layer])

    lon_min, lon_max = pts[:, 0].min(), pts[:, 0].max()
    lat_min, lat_max = pts[:, 1].min(), pts[:, 1].max()

    # Espandi leggermente il bounding box per coprire bene i bordi
    pad_lon = 0.05 * (lon_max - lon_min)
    pad_lat = 0.05 * (lat_max - lat_min)
    lon_grid = np.linspace(lon_min - pad_lon, lon_max + pad_lon, grid_n)
    lat_grid = np.linspace(lat_min - pad_lat, lat_max + pad_lat, grid_n)
    lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)
    grid_pts = np.column_stack([lon_mesh.ravel(), lat_mesh.ravel()])

    # Interpolazione ibrida: linear dove possibile (dentro convex hull),
    # nearest come fallback per i punti fuori hull. Questo produce un
    # campo di flusso denso e visivamente continuo su tutta la griglia.
    u_linear = griddata(pts, u_vals, grid_pts, method='linear')
    u_nearest = griddata(pts, u_vals, grid_pts, method='nearest')
    u_grid = np.where(np.isfinite(u_linear), u_linear, u_nearest)

    v_linear = griddata(pts, v_vals, grid_pts, method='linear')
    v_nearest = griddata(pts, v_vals, grid_pts, method='nearest')
    v_grid = np.where(np.isfinite(v_linear), v_linear, v_nearest)

    err_grid = griddata(pts, err_vals, grid_pts, method='nearest')

    field = []
    for i in range(len(grid_pts)):
        u_i = u_grid[i]
        v_i = v_grid[i]
        if not (np.isfinite(u_i) and np.isfinite(v_i)):
            continue
        err_i = err_grid[i] if np.isfinite(err_grid[i]) else np.nan
        speed_i = float(np.sqrt(u_i**2 + v_i**2))
        direction_i = float(np.degrees(np.arctan2(u_i, v_i)) % 360)
        field.append({
            'station': 'grid',
            'lat': float(grid_pts[i, 1]),
            'lon': float(grid_pts[i, 0]),
            'u': float(u_i),
            'v': float(v_i),
            'speed': speed_i,
            'uerr': float(err_i) if np.isfinite(err_i) else 0.0,
            'direction_deg': direction_i,
        })

    return field


def build_velocity_cones(slices, target_depth, speed_range,
                         visible=True, cone_size_factor=0.015,
                         field=None):
    """Costruisce i coni vettoriali per un singolo strato.

    Fix 1 (vs guidelines3d): il documento usava
    `colorbar=dict(...) if target_depth == 5 else None` ma go.Cone
    non accetta None per colorbar. Qui la colorbar viene passata solo
    quando target_depth corrisponde al primo strato, via kwargs
    condizionale.

    Args:
        slices: dict da extract_depth_slices()
        target_depth: profondita' dello strato (m)
        speed_range: (min, max) per normalizzazione colore
        visible: se il trace e' visibile al caricamento
        cone_size_factor: scala dei coni
        field: lista di punti interpolati da interpolate_velocity_field().
               Se fornito, usa il campo interpolato (griglia densa)
               invece delle sole stazioni. Se None, usa le stazioni.
    """
    layer = field if field is not None else slices.get(target_depth, [])

    if not layer:
        return None

    x = [p['lon'] for p in layer]
    y = [p['lat'] for p in layer]
    z = [-target_depth] * len(layer)
    u = [p['u'] for p in layer]
    v = [p['v'] for p in layer]
    w = [0.0] * len(layer)
    speed = [p['speed'] for p in layer]
    labels = [p['station'] for p in layer]

    hover_text = [
        f"<b>{labels[i]}</b> - {target_depth} m<br>"
        f"U: {u[i]:.3f} m/s<br>"
        f"V: {v[i]:.3f} m/s<br>"
        f"Speed: {speed[i]:.3f} m/s<br>"
        f"Dir: {layer[i].get('direction_deg', 0):.0f}<br>"
        f"Error: {layer[i].get('uerr', 0):.3f} m/s"
        for i in range(len(layer))
    ]

    cone_kwargs = dict(
        x=x, y=y, z=z,
        u=u, v=v, w=w,
        sizemode='absolute',
        sizeref=cone_size_factor,
        colorscale=COLORSCALE_SPEED,
        cmin=speed_range[0],
        cmax=speed_range[1],
        name=f'{target_depth} m',
        text=hover_text,
        hoverinfo='text',
        visible=visible,
        anchor='tail',
    )

    # Colorbar solo sul primo strato (fix bug: None non accettato)
    is_first = (target_depth == sorted(slices.keys())[0])
    if is_first:
        cone_kwargs['showscale'] = True
        cone_kwargs['colorbar'] = dict(
            title=dict(text='Velocita (m/s)', side='right'),
            x=1.12,
            len=0.4,
            y=0.7,
        )
    else:
        cone_kwargs['showscale'] = False

    return go.Cone(**cone_kwargs)


def build_station_columns(stations):
    """Costruisce le colonne verticali alle stazioni.

    Returns:
        list di go.Scatter3d traces (una linea + un label per stazione)
    """
    traces = []

    for stn in stations:
        z_max = -float(np.nanmax(stn['depth']))

        traces.append(go.Scatter3d(
            x=[stn['lon'], stn['lon']],
            y=[stn['lat'], stn['lat']],
            z=[0, z_max],
            mode='lines',
            line=dict(color=STATION_LINE_COLOR, width=2),
            showlegend=False,
            hoverinfo='skip',
        ))

        traces.append(go.Scatter3d(
            x=[stn['lon']],
            y=[stn['lat']],
            z=[2],
            mode='text',
            text=[stn['station']],
            textfont=dict(size=STATION_LABEL_SIZE, color='#3d3d3a'),
            showlegend=False,
            hovertemplate=(
                f"<b>{stn['station']}</b><br>"
                f"Lat: {stn['lat']:.4f}<br>"
                f"Lon: {stn['lon']:.4f}<br>"
                f"Bottom: {stn['bottom_depth']:.0f} m<br>"
                f"Profile depth: {float(np.nanmax(stn['depth'])):.0f} m<br>"
                f"<extra></extra>"
            ),
        ))

    return traces


def build_sea_surface(bathy, opacity=0.15):
    """Costruisce un piano semitrasparente a z=0 per la superficie mare.

    Fix 2 (vs guidelines3d): il documento usava un meshgrid 2x2 (solo
    gli angoli) che produce un piano troppo piccolo e mal renderizzato.
    Qui si usa la griglia bathy completa sottocampionata per un piano
    esteso e visibile.
    """
    # Sottocampiona la griglia bathy a 20x20 per il piano superficie
    n_lat = len(bathy['lat_grid'])
    n_lon = len(bathy['lon_grid'])
    lat_step = max(1, n_lat // 20)
    lon_step = max(1, n_lon // 20)
    lat_sub = bathy['lat_grid'][::lat_step]
    lon_sub = bathy['lon_grid'][::lon_step]
    lon_mesh, lat_mesh = np.meshgrid(lon_sub, lat_sub)
    z_surface = np.zeros_like(lon_mesh, dtype=float)

    return go.Surface(
        x=lon_mesh,
        y=lat_mesh,
        z=z_surface,
        colorscale=[[0, 'rgba(59,139,212,0.3)'],
                    [1, 'rgba(59,139,212,0.3)']],
        showscale=False,
        opacity=opacity,
        name='Superficie',
        hoverinfo='skip',
    )


# ---------- 4. Assemblaggio figura ----------

def build_full_scene(stations, bathy, slices, target_depths,
                     cruise_id='TUNSIC26', show_all_layers=False,
                     interpolate_field=True, grid_n=12):
    """Assembla la scena 3D completa.

    Costruisce una figura Plotly con:
    - Superficie batimetrica GEBCO
    - Piano semitrasparente della superficie del mare
    - Colonne verticali delle stazioni
    - Coni vettoriali per ogni strato (con dropdown di selezione)

    Args:
        stations: lista da load_all_stations()
        bathy: dict da load_bathymetry()
        slices: dict da extract_depth_slices()
        target_depths: lista delle profondita' target
        cruise_id: ID crociera per il titolo
        show_all_layers: se True, mostra tutti gli strati sovrapposti
        interpolate_field: se True (default), interpola U/V su griglia
                           regolare (grid_n x grid_n) per visualizzare
                           un campo di flusso denso invece delle sole
                           frecce alle stazioni
        grid_n: celle per lato della griglia di interpolazione (default 12)

    Returns:
        go.Figure configurata e pronta per export
    """
    fig = go.Figure()

    fig.add_trace(build_sea_surface(bathy))
    fig.add_trace(build_bathymetry_surface(bathy))

    for trace in build_station_columns(stations):
        fig.add_trace(trace)

    all_speeds = []
    for _, layer in slices.items():
        all_speeds.extend([p['speed'] for p in layer])
    speed_range = (0, max(all_speeds) if all_speeds else 0.3)

    n_fixed = len(fig.data)

    # Fix 4: CONE_SIZE_FACTOR calibrato dinamicamente
    cone_size_factor = _compute_cone_size_factor(stations)

    cone_traces = []
    for i, target_z in enumerate(target_depths):
        layer = slices.get(target_z, [])
        field = None
        if interpolate_field and len(layer) >= 3:
            field = interpolate_velocity_field(layer, grid_n=grid_n)

        cone = build_velocity_cones(
            slices, target_z, speed_range,
            visible=(show_all_layers or i == 0),
            cone_size_factor=cone_size_factor,
            field=field,
        )
        if cone is not None:
            cone_traces.append((target_z, cone))
            fig.add_trace(cone)

    # Dropdown per selezione strato
    buttons = []

    all_visible = [True] * n_fixed + [True] * len(cone_traces)
    buttons.append(dict(
        label='Tutti gli strati',
        method='update',
        args=[{'visible': all_visible}],
    ))

    for j, (depth_val, _) in enumerate(cone_traces):
        visibility = [True] * n_fixed
        for k in range(len(cone_traces)):
            visibility.append(k == j)
        buttons.append(dict(
            label=f'{depth_val} m',
            method='update',
            args=[{'visible': visibility}],
        ))

    fig.update_layout(
        updatemenus=[dict(
            type='dropdown',
            direction='down',
            x=0.02,
            y=0.98,
            xanchor='left',
            yanchor='top',
            buttons=buttons,
            bgcolor='rgba(255,255,255,0.9)',
            font=dict(size=12),
            pad=dict(r=10, t=10),
        )],
    )

    fig.update_layout(
        title=dict(
            text=(f'{cruise_id} - Correnti LADCP<br>'
                  f'<sub>{len(stations)} stazioni, '
                  f'{len(target_depths)} strati di profondita</sub>'),
            x=0.5,
            font=dict(size=16),
        ),
        scene=dict(
            xaxis=dict(
                title='Longitudine (E)',
                backgroundcolor='rgba(240,240,235,0.3)',
                gridcolor='rgba(200,200,195,0.3)',
                showbackground=True,
            ),
            yaxis=dict(
                title='Latitudine (N)',
                backgroundcolor='rgba(240,240,235,0.3)',
                gridcolor='rgba(200,200,195,0.3)',
                showbackground=True,
            ),
            zaxis=dict(
                title='Profondita (m)',
                backgroundcolor='rgba(240,240,235,0.3)',
                gridcolor='rgba(200,200,195,0.3)',
                showbackground=True,
                autorange='reversed',
            ),
            aspectmode='manual',
            aspectratio=dict(
                x=1.0,
                y=1.0,
                z=0.5,
            ),
            camera=dict(
                eye=dict(x=1.5, y=-1.5, z=0.8),
                up=dict(x=0, y=0, z=1),
            ),
        ),
        margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(
            x=0.02,
            y=0.5,
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='rgba(200,200,200,0.5)',
            borderwidth=1,
            font=dict(size=11),
        ),
        width=1200,
        height=800,
    )

    return fig


# ---------- 5. Mappe 2D per strato ----------

def build_layer_map(slices, target_depth, bathy=None,
                    interpolate_field=True, grid_n=12):
    """Costruisce una mappa 2D con frecce di corrente per uno strato.

    Sostituisce l'implementazione originale basata su Scattermapbox
    con tile OSM (problemi di licenza). Questa versione usa:
    - go.Contour per le isobate batimetriche (sfondo)
    - go.Scatter per le frecce di corrente (fusto + punta)
    - Annotazioni per le etichette delle stazioni

    Le frecce sono interpolate su griglia regolare (se
    interpolate_field=True) per visualizzare il campo di flusso.

    Args:
        slices: dict da extract_depth_slices()
        target_depth: profondita' dello strato (m)
        bathy: dict da load_bathymetry() per le isobate (opzionale;
               se None, nessuna isobata di sfondo)
        interpolate_field: se True, interpola U/V su griglia densa
        grid_n: celle per lato della griglia di interpolazione

    Returns:
        go.Figure con mappa 2D (asse lon/lat, niente tile esterni)
    """
    layer = slices.get(target_depth, [])
    if not layer:
        return None

    # Campo interpolato per visualizzare il flusso
    field = None
    if interpolate_field and len(layer) >= 3:
        field = interpolate_velocity_field(layer, grid_n=grid_n)
    arrow_points = field if field is not None else layer

    fig = go.Figure()

    # --- Sfondo: isobate batimetriche (contour) ---
    if bathy is not None:
        fig.add_trace(go.Contour(
            z=bathy['elevation'],
            x=bathy['lon_grid'],
            y=bathy['lat_grid'],
            contours=dict(
                start=-800, end=0, size=100,
                showlabels=True,
                labelfont=dict(size=9, color='rgba(40,40,40,0.7)'),
            ),
            colorscale=[[0, '#04342C'], [1, '#9ED4C4']],
            opacity=0.5,
            showscale=False,
            name='Isobate',
            hoverinfo='skip',
            line=dict(width=1, color='rgba(15,110,86,0.6)'),
        ))

    # --- Frecce di corrente ---
    # Scala: gradi per 1 m/s. Calibrata sull'estensione spaziale.
    lons = [p['lon'] for p in arrow_points]
    lats = [p['lat'] for p in arrow_points]
    extent = max(max(lons) - min(lons), max(lats) - min(lats))
    if extent <= 0:
        extent = 1.0
    arrow_scale = 0.15 * extent  # frecce ~15% dell'estensione per 1 m/s

    # Per frecce piu' leggere (punti griglia), riduci opacita'
    is_grid = [p['station'] == 'grid' for p in arrow_points]

    for i, p in enumerate(arrow_points):
        lon0 = p['lon']
        lat0 = p['lat']
        dlon = p['u'] * arrow_scale
        dlat = p['v'] * arrow_scale
        lon1 = lon0 + dlon
        lat1 = lat0 + dlat

        norm_speed = min(p['speed'] / 0.3, 1.0)
        r = int(42 + norm_speed * (227 - 42))
        g = int(120 + norm_speed * (73 - 120))
        b = int(214 + norm_speed * (72 - 214))
        color = f'rgb({r},{g},{b})'
        alpha = 0.5 if is_grid[i] else 1.0
        line_w = 1.5 if is_grid[i] else 3.0

        # Fusto della freccia
        fig.add_trace(go.Scatter(
            x=[lon0, lon1],
            y=[lat0, lat1],
            mode='lines',
            line=dict(width=line_w, color=color),
            opacity=alpha,
            text=f"{p['station']}: {p['speed']:.2f} m/s, dir {p.get('direction_deg', 0):.0f}",
            hoverinfo='text',
            showlegend=False,
        ))

        # Punta (marker triangolo)
        fig.add_trace(go.Scatter(
            x=[lon1],
            y=[lat1],
            mode='markers',
            marker=dict(size=8 if is_grid[i] else 12,
                        symbol='triangle-up',
                        color=color),
            opacity=alpha,
            hoverinfo='skip',
            showlegend=False,
        ))

    # --- Etichette stazioni reali (non grid) ---
    real_stations = [p for p in layer if p['station'] != 'grid']
    for p in real_stations:
        fig.add_trace(go.Scatter(
            x=[p['lon']],
            y=[p['lat']],
            mode='markers+text',
            marker=dict(size=7, color='#3d3d3a', symbol='circle'),
            text=[p['station']],
            textfont=dict(size=9, color='#3d3d3a'),
            textposition='top center',
            showlegend=False,
            hoverinfo='skip',
        ))

    # --- Layout ---
    fig.update_layout(
        title=f'Correnti LADCP a {target_depth} m',
        xaxis=dict(title='Longitudine (E)', scaleanchor='y',
                   scaleratio=1),
        yaxis=dict(title='Latitudine (N)'),
        margin=dict(l=60, r=20, t=50, b=50),
        height=650,
        plot_bgcolor='rgba(245,245,240,0.9)',
    )

    return fig


# ---------- 6. Sezione verticale lungo la rotta ----------

def build_vertical_section(stations, component='speed',
                            max_depth=None):
    """Costruisce una sezione verticale lungo la rotta delle stazioni.

    Le stazioni vengono ordinate per distanza cumulata lungo la rotta
    (formula di Haversine). I profili vengono interpolati su una griglia
    regolare (distanza × profondita') e visualizzati come heatmap.

    Args:
        stations: lista da load_all_stations()
        component: 'u', 'v', 'speed', o 'uerr'
        max_depth: profondita' massima da mostrare (None = auto)

    Returns:
        go.Figure con heatmap
    """
    from scipy.interpolate import griddata

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)
        a = (np.sin(dlat/2)**2 +
             np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) *
             np.sin(dlon/2)**2)
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

    lats = [s['lat'] for s in stations]
    lons = [s['lon'] for s in stations]

    if np.std(lons) > np.std(lats):
        order = np.argsort(lons)
    else:
        order = np.argsort(lats)

    sorted_stations = [stations[i] for i in order]

    cumul_dist = [0.0]
    for i in range(1, len(sorted_stations)):
        d = haversine(
            sorted_stations[i-1]['lat'], sorted_stations[i-1]['lon'],
            sorted_stations[i]['lat'], sorted_stations[i]['lon'])
        cumul_dist.append(cumul_dist[-1] + d)

    all_points = []
    all_values = []

    for i, stn in enumerate(sorted_stations):
        dist = cumul_dist[i]
        z = stn['depth']
        vals = stn[component]

        for j in range(len(z)):
            if np.isfinite(vals[j]):
                all_points.append([dist, z[j]])
                all_values.append(vals[j])

    all_points = np.array(all_points)
    all_values = np.array(all_values)

    if max_depth is None:
        max_depth = float(np.nanmax(all_points[:, 1]))

    dist_grid = np.linspace(0, max(cumul_dist), 200)
    depth_grid = np.linspace(0, max_depth, 150)
    dist_mesh, depth_mesh = np.meshgrid(dist_grid, depth_grid)

    values_grid = griddata(
        all_points, all_values,
        (dist_mesh, depth_mesh),
        method='linear',
    )

    label_map = {
        'u': 'U (East) [m/s]',
        'v': 'V (North) [m/s]',
        'speed': 'Speed [m/s]',
        'uerr': 'Error [m/s]',
    }

    fig = go.Figure()

    fig.add_trace(go.Heatmap(
        x=dist_grid,
        y=depth_grid,
        z=values_grid,
        colorscale=COLORSCALE_SPEED if component == 'speed'
                   else 'RdBu_r',
        colorbar=dict(title=label_map.get(component, component)),
        hovertemplate=(
            'Dist: %{x:.1f} km<br>'
            'Depth: %{y:.0f} m<br>'
            'Value: %{z:.3f}<br>'
            '<extra></extra>'
        ),
    ))

    for i, stn in enumerate(sorted_stations):
        fig.add_trace(go.Scatter(
            x=[cumul_dist[i], cumul_dist[i]],
            y=[0, float(np.nanmax(stn['depth']))],
            mode='lines',
            line=dict(color='rgba(0,0,0,0.3)', width=1, dash='dot'),
            showlegend=False,
            hoverinfo='skip',
        ))
        fig.add_annotation(
            x=cumul_dist[i], y=-10,
            text=stn['station'],
            showarrow=False,
            font=dict(size=9, color='#52514e'),
            yanchor='bottom',
        )

    fig.update_layout(
        yaxis=dict(
            title='Profondita (m)',
            autorange='reversed',
        ),
        xaxis=dict(title='Distanza lungo rotta (km)'),
        title=f'Sezione verticale - {label_map.get(component, component)}',
        height=500,
        margin=dict(t=60, b=60),
    )

    return fig


# Import di plotly.graph_objects lazy (per permettere import del modulo
# anche senza plotly installato, in contesti che non usano la 3D)
def _ensure_plotly():
    """Importa plotly.graph_objects globalmente (lazy)."""
    global go
    import plotly.graph_objects as go


_ensure_plotly()
