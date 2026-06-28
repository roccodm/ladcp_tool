# ladcp_tool/processors/bathy_loader.py
"""Caricamento e preparazione batimetria GEBCO da GeoTIFF.

Il GeoTIFF GEBCO (General Bathymetric Chart of the Oceans) fornisce
elevazione del terreno/fondale in metri su griglia WGS84 (EPSG:4326):
valori positivi = terra sopra il mare, negativi = profondità sottomarina.
"""

import numpy as np


def load_bathymetry(geotiff_path, stations, margin_deg=0.1,
                    max_resolution=200):
    """Carica e ritaglia la batimetria GEBCO dal GeoTIFF.

    Legge il GeoTIFF con rasterio, ritaglia al bounding box delle
    stazioni più un margine configurabile, e sottocampiona a una
    griglia regolare per mantenere il rendering fluido in Plotly.

    Args:
        geotiff_path: path al file GeoTIFF GEBCO
        stations: list of dict con chiavi 'lat', 'lon'
        margin_deg: margine in gradi da aggiungere al bounding box
                    (default 0.1° ≈ 11 km)
        max_resolution: dimensione massima della griglia di output
                        in pixel per lato (default 200×200)

    Returns:
        dict con:
            lon_grid: array 1D delle longitudini (gradi E)
            lat_grid: array 1D delle latitudini (gradi N)
            elevation: array 2D (lat × lon) dei valori di elevazione
                       in metri (negativi = fondale marino)
            depth: array 2D con profondità come valori positivi
                   (per coerenza con le profondità LADCP)
    """
    import rasterio
    from rasterio.windows import from_bounds

    if not stations:
        raise ValueError('no stations provided for bounding box')

    lats = [s['lat'] for s in stations]
    lons = [s['lon'] for s in stations]
    lat_min, lat_max = min(lats) - margin_deg, max(lats) + margin_deg
    lon_min, lon_max = min(lons) - margin_deg, max(lons) + margin_deg

    with rasterio.open(geotiff_path) as src:
        window = from_bounds(lon_min, lat_min, lon_max, lat_max,
                             src.transform)
        elevation = src.read(1, window=window).astype(float)

        win_transform = src.window_transform(window)
        rows, cols = elevation.shape
        lon_full = np.array([win_transform.c + i * win_transform.a
                             for i in range(cols)])
        lat_full = np.array([win_transform.f + j * win_transform.e
                             for j in range(rows)])

        if src.nodata is not None:
            elevation[elevation == src.nodata] = np.nan

    if rows > max_resolution or cols > max_resolution:
        row_step = max(1, rows // max_resolution)
        col_step = max(1, cols // max_resolution)
        elevation = elevation[::row_step, ::col_step]
        lat_full = lat_full[::row_step]
        lon_full = lon_full[::col_step]

    depth = -elevation.copy()
    depth[depth < 0] = 0  # terra = 0 (livello del mare)

    return {
        'lon_grid': lon_full,
        'lat_grid': lat_full,
        'elevation': elevation,
        'depth': depth,
    }


def crop_geotiff(geotiff_path, output_path, lon_min, lat_min,
                 lon_max, lat_max, max_resolution=None):
    """Ritaglia un GeoTIFF GEBCO grande a un tile regionale più piccolo.

    Utility per preparare tile regionali dal dataset GEBCO globale o
    di ampio respierto, prima di usarli con load_bathymetry().

    Args:
        geotiff_path: path al GeoTIFF sorgente (es. Mediterraneo)
        output_path: path del GeoTIFF ritagliato da scrivere
        lon_min, lat_min, lon_max, lat_max: bounding box (WGS84)
        max_resolution: se fornito, sottocampiona il raster di output
                        a questa dimensione massima per lato

    Returns:
        dict con shape del raster scritto e bounding box effettivo
    """
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(geotiff_path) as src:
        window = from_bounds(lon_min, lat_min, lon_max, lat_max,
                             src.transform)
        data = src.read(1, window=window)
        win_transform = src.window_transform(window)

        profile = src.profile.copy()
        profile.update({
            'height': data.shape[0],
            'width': data.shape[1],
            'transform': win_transform,
        })

        if max_resolution and (data.shape[0] > max_resolution
                               or data.shape[1] > max_resolution):
            row_step = max(1, data.shape[0] // max_resolution)
            col_step = max(1, data.shape[1] // max_resolution)
            data = data[::row_step, ::col_step]
            new_transform = rasterio.Affine(
                win_transform.a * col_step, win_transform.b,
                win_transform.c,
                win_transform.d, win_transform.e * row_step,
                win_transform.f,
            )
            profile.update({
                'height': data.shape[0],
                'width': data.shape[1],
                'transform': new_transform,
            })

        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(data, 1)

    return {
        'output_path': str(output_path),
        'shape': data.shape,
        'bounds': (lon_min, lat_min, lon_max, lat_max),
    }
