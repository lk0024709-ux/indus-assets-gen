#!/usr/bin/env bash
# download_assets.sh — fetch the production assets from the GitHub Pages site
# Usage: copy this file to your Godot project root, then: chmod +x download_assets.sh && ./download_assets.sh
set -euo pipefail

BASE_URL="https://lk0024709-ux.github.io/indus-assets-gen/models"
DEST="assets/downloaded_models"

echo "→ Creating $DEST …"
mkdir -p "$DEST/terrain"

echo "→ Downloading the Grand Mahal (docs/models/mahal/rajasthani_mahal_mega.glb, 4.0 MB) …"
curl -L --fail -o "$DEST/rajasthani_mahal_mega.glb" \
  "$BASE_URL/mahal/rajasthani_mahal_mega.glb"
ls -lh "$DEST/rajasthani_mahal_mega.glb"

echo "→ Downloading the 11 Modular Buildings …"
for f in house_blue school_yellow apartment_green warehouse_metal cabin_wood \
         ruined_building shop_row villa_white farmhouse_stone bunker_military tower_sniper; do
  echo "  - $f.glb"
  curl -L --fail -o "$DEST/$f.glb" "$BASE_URL/buildings_modular/$f.glb"
done

echo "→ Downloading the 4 Terrain tiles …"
for f in terrain_ground terrain_hill_large terrain_plateau terrain_valley; do
  echo "  - $f.glb"
  curl -L --fail -o "$DEST/terrain/$f.glb" "$BASE_URL/terrain/$f.glb"
done

echo "→ Done. Verifying:"
ls -lh "$DEST/" "$DEST/terrain/"
echo ""
echo "Place: res://assets/downloaded_models/  (Godot will see these as res://assets/downloaded_models/ …)"
echo "Next: attach examples/godot/main_mahal_godot.gd to your map root — see GODOT_INTEGRATION.md"
