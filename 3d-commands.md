# 3D Viewer — Comandi di generazione

## Prerequisiti

```bash
source /home/rocco/TUNSIC26/.venv/bin/activate
```

## Scene 3D (station-only + interpolata) + layer maps

```bash
python3 /home/rocco/ladcp_tool/current_viewer_tool.py \
    -r /home/rocco/Processed2/output_ladcp_final/results/ \
    -d /home/rocco/Processed2/output_ladcp_final/odv/ \
    -g /home/rocco/ladcp_tool/data/gebco_central_mediterranean.tif \
    -o /home/rocco/Processed2/output_3d_v131/ \
    --all-layers
```

Produce:
- `current_3d_stations.html` — vettori solo alle stazioni
- `current_3d_interpolated.html` — vettori su griglia interpolata 12×12

## Con layer maps (mappe 2D per ogni strato) + PNG

```bash
python3 /home/rocco/ladcp_tool/current_viewer_tool.py \
    -r /home/rocco/Processed2/output_ladcp_final/results/ \
    -d /home/rocco/Processed2/output_ladcp_final/odv/ \
    -g /home/rocco/ladcp_tool/data/gebco_central_mediterranean.tif \
    -o /home/rocco/Processed2/output_3d_v131/ \
    --all-layers --layer-maps --export-png
```

Produce:
- `layer_maps/layer_{depth}m.html` per ogni strato
- `layer_maps/layer_{depth}m.png` (~250 KB ciascuno)

## Sezione verticale (opzionale)

```bash
python3 /home/rocco/ladcp_tool/current_viewer_tool.py \
    -r /home/rocco/Processed2/output_ladcp_final/results/ \
    -d /home/rocco/Processed2/output_ladcp_final/odv/ \
    -g /home/rocco/ladcp_tool/data/gebco_central_mediterranean.tif \
    -o /home/rocco/Processed2/output_3d_v131/section_speed.html \
    --section speed
```

## Flag utili

| Flag | Descrizione |
|------|-------------|
| `--depths 5,10,50,100,200` | Strati personalizzati (default: 5,10,25,50,100,150,200,300) |
| `--all-layers` | Mostra tutti gli strati sovrapposti all'apertura |
| `--no-interpolate` | Disabilita il campo interpolato (solo stazioni) |
| `--grid-n 8` | Griglia interpolazione piu' rada (default: 12) |
| `--export-png` | Esporta layer maps anche in PNG (richiede Chrome) |
| `--bathy-resolution 100` | Riduce risoluzione GEBCO per debug |
| `--bathy-margin 0.2` | Margine GEBCO intorno alle stazioni (gradi) |
