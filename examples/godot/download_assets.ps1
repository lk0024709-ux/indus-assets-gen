# download_assets.ps1 — TASK 1 helper for Godot project (Windows PowerShell)
# Usage: copy to your Godot project root, then:  powershell -ExecutionPolicy Bypass -File download_assets.ps1

$BaseUrl = "https://lk0024709-ux.github.io/indus-assets-gen/models"
$Dest = "assets/downloaded_models"
$ModularDest = "$Dest/modular"

Write-Host "→ Creating $Dest …"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
New-Item -ItemType Directory -Force -Path $ModularDest | Out-Null

Write-Host "→ Downloading rajasthani_mahal.glb (4.2 MB) …"
Invoke-WebRequest -Uri "$BaseUrl/buildings/rajasthani_mahal.glb" -OutFile "$Dest/rajasthani_mahal.glb"
Copy-Item "$Dest/rajasthani_mahal.glb" "$Dest/mahal_palace_master.glb" -ErrorAction SilentlyContinue
Get-ChildItem "$Dest/rajasthani_mahal.glb" | Format-List Length, Name

Write-Host "→ Downloading modular blocks (4) …"
@("wall_block","arch_block","dome","pillar") | ForEach-Object {
  Write-Host "  - $_.glb"
  Invoke-WebRequest -Uri "$BaseUrl/modular/$_.glb" -OutFile "$ModularDest/$_.glb"
}
Copy-Item "$ModularDest/wall_block.glb" "$ModularDest/wall_module.glb" -ErrorAction SilentlyContinue
Copy-Item "$ModularDest/arch_block.glb" "$ModularDest/arch_module.glb" -ErrorAction SilentlyContinue
Copy-Item "$ModularDest/dome.glb" "$ModularDest/dome_module.glb" -ErrorAction SilentlyContinue
Copy-Item "$ModularDest/pillar.glb" "$ModularDest/pillar_module.glb" -ErrorAction SilentlyContinue

Write-Host "→ Done. Verifying:"
Get-ChildItem $Dest, $ModularDest | Format-Table Name, Length
Write-Host "Place: res://assets/downloaded_models/"
Write-Host "Next: See GODOT_INTEGRATION.md Task 2 + examples/godot/main_mahal_godot.gd"
