#!/usr/bin/env python3
"""
current_viewer_tool - Visualizzazione 3D interattiva delle correnti LADCP.

Legge gli output di ladcp_tool (velocity profiles + ODV spreadsheets),
carica la batimetria GEBCO da GeoTIFF, e produce una scena 3D interattiva
esportata come file HTML autonomo apribile nel browser.

Usage:
    current_viewer_tool \\
        --results-dir ./ladcp_output/results \\
        --odv-dir ./ladcp_output/odv \\
        --gebco ./gebco_central_mediterranean.tif \\
        --output ./current_view.html

    current_viewer_tool \\
        --results-dir ./ladcp_output/results \\
        --odv-dir ./ladcp_output/odv \\
        --gebco ./gebco.tif \\
        --output ./views/ \\
        --depths 5,10,50,100,200 \\
        --section speed \\
        --layer-maps
"""

import sys
import argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ladcp_tool.outputs.current_viewer import (
    load_all_stations,
    extract_depth_slices,
    build_full_scene,
    build_layer_map,
    build_vertical_section,
)
from ladcp_tool.processors.bathy_loader import load_bathymetry


def main():
    parser = argparse.ArgumentParser(
        description='Visualizzazione 3D delle correnti LADCP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  current_viewer_tool -r ./results -d ./odv -g ./gebco.tif -o ./view.html
  current_viewer_tool -r ./results -d ./odv -g ./gebco.tif -o ./views/ \\
      --depths 5,10,50,100,200 --section speed --layer-maps
""")

    parser.add_argument('-r', '--results-dir', required=True,
                        help='Directory con *_velocity_profile.txt')
    parser.add_argument('-d', '--odv-dir', required=True,
                        help='Directory con *_LADCP.txt (ODV headers)')
    parser.add_argument('-g', '--gebco', required=True,
                        help='Path al GeoTIFF GEBCO della batimetria')
    parser.add_argument('-o', '--output', default='./current_view.html',
                        help='File HTML di output (o directory per multi-file)')
    parser.add_argument('--cruise-id', default='TUNSIC26',
                        help='Cruise ID (default: TUNSIC26)')

    parser.add_argument('--depths', default='5,10,25,50,100,150,200,300',
                        help='Profondita target (m), separate da virgola')
    parser.add_argument('--bathy-resolution', type=int, default=200,
                        help='Risoluzione griglia batimetrica (pixel/lato)')
    parser.add_argument('--bathy-margin', type=float, default=0.1,
                        help='Margine intorno alle stazioni (gradi)')

    parser.add_argument('--section', nargs='?', const='speed',
                        choices=['u', 'v', 'speed', 'uerr'],
                        help='Genera sezione verticale (default: speed)')
    parser.add_argument('--layer-maps', action='store_true',
                        help='Genera mappe 2D per ogni strato')
    parser.add_argument('--all-layers', action='store_true',
                        help='Mostra tutti gli strati sovrapposti al caricamento')

    args = parser.parse_args()

    target_depths = [int(d) for d in args.depths.split(',')]
    output = Path(args.output)

    print('=' * 60)
    print('  current_viewer_tool - LADCP Current Visualization')
    print(f'  Results: {args.results_dir}')
    print(f'  ODV:     {args.odv_dir}')
    print(f'  GEBCO:   {args.gebco}')
    print(f'  Depths:  {target_depths}')
    print('=' * 60)

    # --- 1. Carica dati ---
    stations = load_all_stations(
        args.results_dir, args.odv_dir, args.cruise_id)

    if not stations:
        print('ERROR: No stations loaded. Check paths.')
        sys.exit(1)

    # --- 2. Carica batimetria ---
    print(f'  Loading GEBCO bathymetry...')
    bathy = load_bathymetry(
        args.gebco, stations,
        margin_deg=args.bathy_margin,
        max_resolution=args.bathy_resolution)
    print(f'  Bathymetry grid: {len(bathy["lat_grid"])}x'
          f'{len(bathy["lon_grid"])} '
          f'(elevation {bathy["elevation"].min():.0f} to '
          f'{bathy["elevation"].max():.0f} m)')

    # --- 3. Estrai strati ---
    slices = extract_depth_slices(stations, target_depths)
    for d, layer in slices.items():
        print(f'  Depth {d:>4d} m: {len(layer)} stations')

    # --- 4. Costruisci scena 3D ---
    print(f'  Building 3D scene...')
    fig_3d = build_full_scene(
        stations, bathy, slices, target_depths,
        cruise_id=args.cruise_id,
        show_all_layers=args.all_layers)

    # --- 5. Export ---
    if output.suffix == '.html':
        output.parent.mkdir(exist_ok=True, parents=True)
        fig_3d.write_html(
            str(output),
            include_plotlyjs=True,
            full_html=True,
            config={
                'displayModeBar': True,
                'scrollZoom': True,
                'modeBarButtonsToAdd': ['downloadImage'],
            },
        )
        print(f'  3D scene: {output}')
    else:
        output.mkdir(exist_ok=True, parents=True)
        fig_3d.write_html(str(output / 'current_3d.html'),
                          include_plotlyjs=True, full_html=True)
        print(f'  3D scene: {output / "current_3d.html"}')

    # --- 6. Sezione verticale (opzionale) ---
    if args.section:
        print(f'  Building vertical section ({args.section})...')
        fig_sec = build_vertical_section(stations, component=args.section)
        sec_path = (output.parent if output.suffix == '.html'
                    else output) / f'section_{args.section}.html'
        fig_sec.write_html(str(sec_path), include_plotlyjs=True,
                           full_html=True)
        print(f'  Section:  {sec_path}')

    # --- 7. Mappe 2D per strato (opzionale) ---
    if args.layer_maps:
        map_dir = (output.parent if output.suffix == '.html'
                   else output) / 'layer_maps'
        map_dir.mkdir(exist_ok=True, parents=True)
        for d in target_depths:
            fig_map = build_layer_map(slices, d)
            if fig_map:
                map_path = map_dir / f'layer_{d:04d}m.html'
                fig_map.write_html(str(map_path),
                                   include_plotlyjs=True,
                                   full_html=True)
                print(f'  Layer map: {map_path}')

    print(f'\n  Done. Open HTML files in browser.')


if __name__ == '__main__':
    main()
