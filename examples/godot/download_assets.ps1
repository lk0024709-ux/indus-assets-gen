# download_assets.ps1 — fetch the production assets from the GitHub Pages site (Windows)
# Usage: copy this file to your Godot project root, then: powershell -ExecutionPolicy Bypass -File .\download_assets.ps1
$ErrorActionPreference = "Stop"

$BaseUrl = "https://lk0024709-ux.github.io/indus-assets-gen/models"
$Dest    = "assets/downloaded_models"

Write-Host "-> Creating $Dest ..."
New-Item -ItemType Directory -Force -Path "$Dest/terrain" | Out-Null

Write-Host "-> Downloading the Grand Mahal (rajasthani_mahal_mega.glb, 4.0 MB) ..."
Invoke-WebRequest -Uri "$BaseUrl/mahal/rajasthani_mahal_mega.glb" -OutFile "$Dest/rajasthani_mahal_mega.glb"
Get-ChildItem "$Dest/rajasthani_mahal_mega.glb" | Format-List Length, Name

Write-Host "-> Downloading the 11 Modular Buildings ..."
@("house_blue","school_yellow","apartment_green","warehouse_metal","cabin_wood",
  "ruined_building","shop_row","villa_white","farmhouse_stone","bunker_military","tower_sniper") | ForEach-Object {
  Write-Host "  - $_.glb"
  Invoke-WebRequest -Uri "$BaseUrl/buildings_modular/$_.glb" -OutFile "$Dest/$_.glb"
}

Write-Host "-> Downloading the 4 Terrain tiles ..."
@("terrain_ground","terrain_hill_large","terrain_plateau","terrain_valley") | ForEach-Object {
  Write-Host "  - $_.glb"
  Invoke-WebRequest -Uri "$BaseUrl/terrain/$_.glb" -OutFile "$Dest/terrain/$_.glb"
}

Write-Host "-> Done. Verifying:"
Get-ChildItem "$Dest" -Recurse -Filter *.glb | Format-Table Length, FullName
Write-Host "Place: res://assets/downloaded_models/  — see GODOT_INTEGRATION.md"
