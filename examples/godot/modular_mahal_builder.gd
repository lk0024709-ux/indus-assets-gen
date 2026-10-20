# modular_mahal_builder.gd — TASK 3: Optional runtime assembly from modular blocks
# Godot 4.2+ | Use when full rajasthani_mahal.glb (4.2 MB, ~9816 tris, 23 mats) is too heavy for low-end devices.
# It rebuilds a simplified Mahal at runtime from the 4 modular blocks (wall/arch/dome/pillar) — same specs as tools/generate_modular.py
#
# Blocks (hosted after deploy, or local at res://assets/downloaded_models/modular/):
#   wall_block.glb  / wall_module.glb  — 10×0.5×4 + gold border 10×0.6×0.3, SalmonPink/GoldYellow
#   arch_block.glb / arch_module.glb  — 10×0.5×6 with 4×1×4 box + r2 cyl UNION→DIFFERENCE + gold torus frame, bbox 10×0.6×6.12
#   dome.glb / dome_module.glb        — r=5 hemisphere + spire cyl r0.3 h3 + cone r0.45, TealCyan/GoldYellow
#   pillar.glb / pillar_module.glb    — r0.5 h6 + 3 torus bands r0.52 @0.6/3.0/5.4, SandstoneBeige + Red/Blue/Yellow
#
# References Master dimensions (tools/generate_mahal_master.py):
#   BASE_W 40 × BASE_D 30 × BASE_H 1, BUILD_W 30 × BUILD_D 20 × BUILD_H 12, WALL_THICK 0.8,
#   CENTRAL_DOME_R 6, CORNER_DOME_R 3, CHHATRI_DOME_R 1.4
#
# Usage in main.gd:
#   const ModularBuilder = preload("res://examples/godot/modular_mahal_builder.gd")
#   if OS.get_name() == "Android" and OS.get_static_memory_usage() > MEMORY_THRESHOLD:
#       ModularBuilder.assemble_at(Vector3.ZERO, self)
#   else:
#       $MainMahalLoader.load_full_mahal_at(Vector3.ZERO)
#
# Each module also gets ConcavePolygonShape3D trimesh so walking/climbing works.

extends Node
class_name ModularMahalBuilder

const MODULAR_DIR := "res://assets/downloaded_models/modular"

# Tune density vs perf
@export var use_trimesh: bool = true
@export var collision_layer: int = 1
@export var collision_mask: int = 1

# Master-aligned layout constants
const BUILD_W: float = 30.0
const BUILD_D: float = 20.0
const BUILD_H: float = 12.0
const BASE_W: float = 40.0
const BASE_D: float = 30.0
const CENTRAL_DOME_R: float = 6.0
const CORNER_DOME_R: float = 3.0

## Public entry — call from main.gd or _ready
static func assemble_at(center: Vector3, parent: Node) -> Node3D:
	var builder := ModularMahalBuilder.new()
	builder.name = "ModularMahal"
	parent.add_child(builder)
	builder._assemble(center)
	return builder

func _assemble(center: Vector3) -> void:
	# Ensure parent is 3D
	var root := Node3D.new()
	root.name = "AssemblyRoot"
	root.position = center
	add_child(root)

	# 1. Ground/base (optional — if you don't already have terrain_ground at y=0)
	# We don't ship a base_ground.glb in modular/; reuse your existing terrain. Uncomment to add a simple plane:
	# _add_base_plane(root, center)

	# 2. Walls — rebuild 30×20×12 perimeter using wall + arch blocks
	# Original has 3 front arches + 2 sides + interior jali; we approximate with arch blocks at key positions
	_print_header("Walls & Arches (30×20×12)")

	# Front wall (z = +BUILD_D/2), back wall (z = -BUILD_D/2): each 30 m wide → 3× wall_block (10 m) = 30 m
	# Replace middle segment with arch_block to keep opening
	for side in [1, -1]: # 1 front, -1 back
		var z: float = side * BUILD_D / 2.0
		# left segment, arch, right segment (arch is wider due to opening but still 10 m bbox)
		var x_positions := [-10.0, 0.0, 10.0]
		for i in range(3):
			var x: float = x_positions[i]
			var is_arch := (i == 1) # center is arch
			var glb_name := "arch_block.glb" if is_arch else "wall_block.glb"
			# Fallback to _module alias
			var inst := _instance_glb(glb_name, root, Vector3(x, 0, z))
			if inst == null:
				glb_name = "arch_module.glb" if is_arch else "wall_module.glb"
				inst = _instance_glb(glb_name, root, Vector3(x, 0, z))
			if inst:
				# Arch wall is taller (6 m vs 4 m) — Master walls are 12 m, but modular arch is 6 m.
				# Scale Y by 2 to reach 12 m, or stack two. We stack 2 for better texel density:
				if is_arch:
					# Bottom half already placed; add upper extension if needed for 12 m
					# For demo we keep 6 m — double if you need full 12 m:
					# var upper := _instance_glb(glb_name, root, Vector3(x, 6, z))
					pass

	# Side walls (x = ±BUILD_W/2, extend in Z): BUILD_D 20 m → 2× wall_block (10 m) along Z
	for side in [1, -1]: # 1 right, -1 left
		var x: float = side * BUILD_W / 2.0
		for seg in [-5.0, 5.0]: # two 10 m segments along Z
			var inst := _instance_glb("wall_block.glb", root, Vector3(x, 0, seg))
			if inst == null:
				inst = _instance_glb("wall_module.glb", root, Vector3(x, 0, seg))
			if inst:
				inst.rotation.y = PI / 2 # rotate to run along Z (wall default runs along X, depth 0.5)
				# Fix physics shape rotation already baked — re-generate after rotation:
				# _regenerate_collision(inst) — handled inside _instance_glb after add

	_print_header("Pillars (8 interior + jharokha)")

	# 3. Pillars — 8 interior pillars mimicking Master's Darbar (4 corners of inner 3×3 grid + 4 mid)
	var pillar_positions: Array[Vector3] = [
		Vector3(-9, 0, -6), Vector3(9, 0, -6), Vector3(-9, 0, 6), Vector3(9, 0, 6),
		Vector3(0, 0, -6), Vector3(0, 0, 6), Vector3(-9, 0, 0), Vector3(9, 0, 0),
	]
	for pos in pillar_positions:
		var inst := _instance_glb("pillar.glb", root, pos)
		if inst == null:
			inst = _instance_glb("pillar_module.glb", root, pos)
		# pillar is 6 m tall — for 12 m walls, stack second pillar at y=6
		# Uncomment for full-height pillars:
		# var upper := _instance_glb("pillar.glb", root, pos + Vector3(0,6,0))

	# Jharokha pillars (protruding balconies) — 2 small pillars per jharokha, front/side
	for x in [-10.0, 0.0, 10.0]:
		var z_front: float = BUILD_D/2 + 1.0 # protrude 1 m out
		var left_pillar := _instance_glb("pillar.glb", root, Vector3(x - 0.5, 7, z_front))
		if left_pillar:
			left_pillar.scale = Vector3(0.25, 0.25, 0.25) # r0.12 vs r0.5 ≈ 0.24×
		var right_pillar := _instance_glb("pillar.glb", root, Vector3(x + 0.5, 7, z_front))
		if right_pillar:
			right_pillar.scale = Vector3(0.25, 0.25, 0.25)

	_print_header("Domes (central r6 + 4 corners r3 scaled)")

	# 4. Domes — central teal r6 + 4 yellow corners r3 (modular dome is r5, scale accordingly)
	# Master: central at (0, BUILD_H, 0) r6; corners at (±10, BUILD_H, ±7) r3  — approx
	var central := _instance_glb("dome.glb", root, Vector3(0, BUILD_H, 0))
	if central == null:
		central = _instance_glb("dome_module.glb", root, Vector3(0, BUILD_H, 0))
	if central:
		central.scale = Vector3(CENTRAL_DOME_R/5.0, CENTRAL_DOME_R/5.0, CENTRAL_DOME_R/5.0) # 6/5 = 1.2×

	var corner_offsets: Array[Vector3] = [
		Vector3(10, BUILD_H, 7), Vector3(-10, BUILD_H, 7),
		Vector3(10, BUILD_H, -7), Vector3(-10, BUILD_H, -7),
	]
	for off in corner_offsets:
		var c := _instance_glb("dome.glb", root, off)
		if c == null:
			c = _instance_glb("dome_module.glb", root, off)
		if c:
			c.scale = Vector3(CORNER_DOME_R/5.0, CORNER_DOME_R/5.0, CORNER_DOME_R/5.0) # 0.6×

	# Chhatri mini-domes (optional, 4 corners of base)
	for off in [Vector3(14, 1, 9), Vector3(-14, 1, 9), Vector3(14, 1, -9), Vector3(-14, 1, -9)]:
		var ch := _instance_glb("dome.glb", root, off)
		if ch == null:
			ch = _instance_glb("dome_module.glb", root, off)
		if ch:
			ch.scale = Vector3(1.4/5.0, 1.4/5.0, 1.4/5.0)

	# Jharokha half-domes — reuse dome scaled tiny + offset to sit on balcony
	for x in [-10.0, 0.0, 10.0]:
		var jd := _instance_glb("dome.glb", root, Vector3(x, 10.5, BUILD_D/2 + 1.0))
		if jd == null:
			jd = _instance_glb("dome_module.glb", root, Vector3(x, 10.5, BUILD_D/2 + 1.0))
		if jd:
			jd.scale = Vector3(0.3, 0.3, 0.3) # 1.5/5 = 0.3

	print("[ModularMahal] Assembly complete at %s — front:3 arch/wall, sides:4, pillars:8+6, domes:1+4+4+3" % center)

# Helpers

func _instance_glb(glb_name: String, parent: Node3D, pos: Vector3) -> Node3D:
	var path := "%s/%s" % [MODULAR_DIR, glb_name]
	if not FileAccess.file_exists(path):
		# Try alternate directory the user might use (flat)
		path = "res://assets/downloaded_models/%s" % glb_name
		if not FileAccess.file_exists(path):
			push_warning("[ModularMahal] Missing %s — run Task 1 download" % glb_name)
			return null

	var state := GLTFDocument.new()
	var gltf_state := GLTFState.new()
	var err := state.append_from_file(path, gltf_state)
	if err != OK:
		push_error("[ModularMahal] GLTF load failed %s err=%d" % [path, err])
		return null
	var scene: Node = state.generate_scene(gltf_state)
	if scene == null:
		return null
	var nd: Node3D = scene as Node3D
	if nd == null:
		var w := Node3D.new()
		w.add_child(scene)
		nd = w
	nd.position = pos
	nd.name = glb_name.get_basename().capitalize() + "_%d_%d" % [int(pos.x*10), int(pos.z*10)]
	parent.add_child(nd)

	# Generate trimesh collision for every mesh in this module
	if use_trimesh:
		_generate_trimesh_for_subtree(nd)
	return nd

func _generate_trimesh_for_subtree(root: Node) -> void:
	for c in root.get_children():
		_generate_trimesh_for_subtree(c)
	if root is MeshInstance3D:
		var mi := root as MeshInstance3D
		if mi.mesh == null: return
		var shape: Shape3D = mi.mesh.create_trimesh_shape()
		if shape == null: return
		var body := StaticBody3D.new()
		body.name = mi.name + "_Col"
		body.collision_layer = collision_layer
		body.collision_mask = collision_mask
		var cs := CollisionShape3D.new()
		cs.shape = shape
		body.add_child(cs)
		mi.add_child(body)

func _add_base_plane(parent: Node3D, center: Vector3) -> void:
	# Fallback simple plane if you have no terrain — 40×30 base at y=0
	var mesh_inst := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(BASE_W, BASE_D)
	mesh_inst.mesh = plane
	mesh_inst.position = center
	mesh_inst.name = "BasePlane"
	parent.add_child(mesh_inst)
	var body := StaticBody3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(BASE_W, 0.2, BASE_D)
	var cs := CollisionShape3D.new()
	cs.shape = shape
	cs.position.y = -0.1
	body.add_child(cs)
	mesh_inst.add_child(body)

func _print_header(msg: String) -> void:
	print("— [ModularMahal] %s —" % msg)
