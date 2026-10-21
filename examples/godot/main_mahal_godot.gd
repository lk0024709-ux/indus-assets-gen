# main_mahal_godot.gd — load the Grand Mahal (rajasthani_mahal_mega.glb) into your Godot map
# Godot 4.2+ | Place this script on your map root (Node3D) or autoload it from main.gd
# Requires: res://assets/downloaded_models/rajasthani_mahal_mega.glb
#
# What it does:
# - Removes old procedural Mahal if present (looks for %OldMahal, $OldMahal, "Mahal", "ProceduralMahal")
# - Loads the new GLB at (0,0,0) — the file's origin is bottom-center (0,0,0) so no offset needed
# - Generates StaticBody3D + ConcavePolygonShape3D (trimesh) for every MeshInstance3D so stairs/jali/interior work
# - Optional: rebakes Navigation if you use NavigationServer3D
#
# Usage:
#   1) Put rajasthani_mahal_mega.glb at res://assets/downloaded_models/rajasthani_mahal_mega.glb (see GODOT_INTEGRATION.md)
#   2) Attach this script to your World/Map node, set `mahal_glb_path` in Inspector, run.
#   3) Remove your old `generate_mahal()` call — or leave it, this script auto-removes it.
#
# Import tip (Editor): Select rajasthani_mahal_mega.glb in FileSystem → Import → Root Type = Node3D, Generate Collisions = OFF
# We generate accurate trimesh ourselves (convex would seal archways).

extends Node3D
class_name MainMahalLoader

## Path inside res:// (must exist). Source: docs/models/mahal/rajasthani_mahal_mega.glb
@export var mahal_glb_path: String = "res://assets/downloaded_models/rajasthani_mahal_mega.glb"
## Fallback path (older download name kept by some projects)
@export var mahal_fallback_path: String = "res://assets/downloaded_models/rajasthani_mahal.glb"
## Map center — per spec, exactly (0,0,0). Change only if your terrain is offset.
@export var mahal_position: Vector3 = Vector3.ZERO
## Collision layers — adjust to your player/world
@export var collision_layer: int = 1
@export var collision_mask: int = 1
## Auto-remove old procedural mahal nodes (names to try)
@export var old_mahal_node_names: Array[String] = ["OldMahal", "Mahal", "ProceduralMahal", "mahal", "MAHAL"]
## Re-bake NavigationMesh after spawn (if you have a NavigationRegion3D)
@export var rebake_navigation: bool = false
@export var navigation_region_path: NodePath = NodePath()

var _mahal_root: Node3D = null

func _ready() -> void:
	# 1. Remove old procedural Mahal
	_remove_old_mahal()

	# 2. Load + instance new Mahal at center
	var ok := load_full_mahal_at(mahal_position)
	if not ok:
		push_error("[MainMahal] Failed to load any GLB. Checked: %s and %s" % [mahal_glb_path, mahal_fallback_path])

	# 3. Optional nav rebake (deferred, after collisions enter tree)
	if rebake_navigation:
		call_deferred("_rebake_nav")

# Public API — call from main.gd if you prefer manual control
func load_full_mahal_at(pos: Vector3) -> bool:
	var glb_path := _resolve_glb_path()
	if glb_path.is_empty():
		push_error("[MainMahal] GLB not found at %s nor %s — run Task 1 download step (see GODOT_INTEGRATION.md)" % [mahal_glb_path, mahal_fallback_path])
		return false

	var state := GLTFDocument.new()
	var gltf_state := GLTFState.new()
	# Optional: tune import (KHR_lights_punctual, textures)
	var err := state.append_from_file(glb_path, gltf_state)
	if err != OK:
		push_error("[MainMahal] GLTFDocument.append_from_file failed %s err=%d" % [glb_path, err])
		return false

	var root: Node = state.generate_scene(gltf_state)
	if root == null:
		push_error("[MainMahal] generate_scene returned null")
		return false

	# Ensure we operate on Node3D
	if root is not Node3D:
		var wrapper := Node3D.new()
		wrapper.add_child(root)
		root = wrapper

	_mahal_root = root as Node3D
	_mahal_root.name = "RajasthaniMahal"
	_mahal_root.position = pos  # (0,0,0) — GLB bottom-center origin, no y-offset needed
	add_child(_mahal_root)

	# 2b. Generate trimesh collisions recursively
	var mesh_count := _generate_trimesh_collisions_recursive(_mahal_root)
	print("[MainMahal] Loaded %s at %s → %d MeshInstance3D with ConcavePolygonShape3D (pos=%s)" % [glb_path, pos, mesh_count, pos])

	# 2c. Make sure it's visible + casts shadows (GLB may have materials with low roughness)
	_mahal_root.visible = true
	return true

func _resolve_glb_path() -> String:
	if FileAccess.file_exists(mahal_glb_path):
		return mahal_glb_path
	if FileAccess.file_exists(mahal_fallback_path):
		return mahal_fallback_path
	# Also try the original repo names if user downloaded verbatim
	for p in ["res://assets/downloaded_models/mahal/rajasthani_mahal_mega.glb",
			  "res://assets/downloaded_models/rooms/room_darbar_hall.glb"]:
		if FileAccess.file_exists(p):
			return p
	return ""

func _remove_old_mahal() -> void:
	# Try named nodes first
	for name in old_mahal_node_names:
		var n := get_node_or_null(NodePath(name))
		if n:
			print("[MainMahal] Removing old procedural node: ", n.get_path())
			n.queue_free()
		# also check inside children recursively? common to be under World/Map
		var found := _find_child_by_name_recursive(self, name)
		if found and found != n:
			print("[MainMahal] Removing old procedural child: ", found.get_path())
			found.queue_free()

	# Also nuke nodes that look like procedural mahal groups ( heuristic: has many MeshInstance3D + name contains mahal )
	# Uncomment if your old generator left orphans:
	# _remove_by_heuristic()

func _find_child_by_name_recursive(node: Node, target: String) -> Node:
	if node.name == target:
		return node
	for c in node.get_children():
		var r := _find_child_by_name_recursive(c, target)
		if r: return r
	return null

# Generates StaticBody3D + ConcavePolygonShape3D (trimesh) for the entire Mahal so players can walk inside, climb stairs, and collisions work perfectly.
# Uses mesh.create_trimesh_shape() — the only shape that respects interior, arch holes, and stair steps.
# Do NOT use Convex or Box — archways will become blocked.
func _generate_trimesh_collisions_recursive(root: Node) -> int:
	var count := 0
	for child in root.get_children():
		count += _generate_trimesh_collisions_recursive(child) # recurse first

	# Only MeshInstance3D matters
	if root is MeshInstance3D:
		var mi: MeshInstance3D = root as MeshInstance3D
		if mi.mesh == null:
			return count

		# Skip tiny decorative meshes if you want (optional optimization):
		# if _aabb_volume(mi) < 0.01: continue

		var shape: Shape3D = mi.mesh.create_trimesh_shape()
		if shape == null:
			# Fallback: try convex (shouldn't happen) — log and continue
			push_warning("[MainMahal] create_trimesh_shape null for %s, skipping" % mi.name)
			continue

		# ConcavePolygonShape3D is the trimesh type
		var body := StaticBody3D.new()
		body.name = mi.name + "_Col"
		body.collision_layer = collision_layer
		body.collision_mask = collision_mask
		# Keep transform relative to mesh — body as child of mi inherits its transform
		var col_shape := CollisionShape3D.new()
		col_shape.shape = shape
		col_shape.name = "CollisionShape3D"
		body.add_child(col_shape)

		# Optionally enable useful flags
		# body.physics_material_override = PhysicsMaterial.new()  # set friction if stairs are slippery

		mi.add_child(body)
		count += 1

		# Ensure mesh casts shadows / is visible
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	return count

func _rebake_nav() -> void:
	if navigation_region_path.is_empty():
		return
	var region := get_node_or_null(navigation_region_path)
	if region == null:
		push_warning("[MainMahal] navigation_region_path not found: %s" % navigation_region_path)
		return
	if region.has_method("bake_navigation_mesh"):
		region.bake_navigation_mesh()
		print("[MainMahal] Navigation rebaked")
	else:
		# Godot 4 NavigationServer API
		pass

# Utility — if you want to cull tiny meshes from collision (optional, saves physics time)
func _aabb_volume(mi: MeshInstance3D) -> float:
	var aabb: AABB = mi.mesh.get_aabb() if mi.mesh else AABB()
	return aabb.size.x * aabb.size.y * aabb.size.z

# Clean up
func remove_mahal() -> void:
	if _mahal_root and is_instance_valid(_mahal_root):
		_mahal_root.queue_free()
		_mahal_root = null
