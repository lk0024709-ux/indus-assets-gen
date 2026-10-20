#!/usr/bin/env bash
# download_assets.sh — TASK 1 helper for Godot project (Linux/macOS)
# Fetches rajasthani_mahal.glb + modular blocks from the asset repo's GitHub Pages
# Usage: copy this file to your Godot project root, then:  chmod +x download_assets.sh && ./download_assets.sh
set -euo pipefail

BASE_URL="https://lk0024709-ux.github.io/indus-assets-gen/models"
DEST="assets/downloaded_models"
MODULAR_DEST="$DEST/modular"

echo "→ Creating $DEST …"
mkdir -p "$DEST" "$MODULAR_DEST"

echo "→ Downloading rajasthani_mahal.glb (alias of mahal_palace_master.glb, 4.2 MB) …"
curl -L --fail -o "$DEST/rajasthani_mahal.glb" "$BASE_URL/buildings/rajasthani_mahal.glb"
# Also keep fallback name some scripts expect
cp "$DEST/rajasthani_mahal.glb" "$DEST/mahal_palace_master.glb" 2>/dev/null || true
ls -lh "$DEST/rajasthani_mahal.glb"

echo "→ Downloading modular blocks (4) …"
for f in wall_block arch_block dome pillar; do
  echo "  - $f.glb"
  curl -L --fail -o "$MODULAR_DEST/${f}.glb" "$BASE_URL/modular/${f}.glb"
  # Create _module alias (some GDScript expects dome_module.glb etc.)
  cp "$MODULAR_DEST/${f}.glb" "$MODULAR_DEST/${f%_block*}_module.glb" 2>/dev/null || cp "$MODULAR_DEST/${f}.glb" "$MODULAR_DEST/${f%.glb}_module.glb" || true
done

# Explicit alias copies (ensures exact names task 3 mentions)
cp "$MODULAR_DEST/wall_block.glb" "$MODULAR_DEST/wall_module.glb" 2>/dev/null || true
cp "$MODULAR_DEST/arch_block.glb" "$MODULAR_DEST/arch_module.glb" 2>/dev/null || true
cp "$MODULAR_DEST/dome.glb" "$MODULAR_DEST/dome_module.glb" 2>/dev/null || true
cp "$MODULAR_DEST/pillar.glb" "$MODULAR_DEST/pillar_module.glb" 2>/dev/null || true

echo "→ Done. Verifying:"
ls -lh "$DEST/" "$MODULAR_DEST/"
echo ""
echo "Place: res://assets/downloaded_models/  (Godot will see these as res://assets/downloaded_models/ …)"
echo "Next: Replace old procedural Mahal in main.gd — see GODOT_INTEGRATION.md Task 2 + examples/godot/main_mahal_godot.gd"
