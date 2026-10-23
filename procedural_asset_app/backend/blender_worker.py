import json, sys
import bpy
from recipes import chair, table, lamp, rock, barrel
from recipes.base import clear_scene

MODULES = {"chair":chair,"table":table,"lamp":lamp,"rock":rock,"barrel":barrel}

def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if len(args)!=3:
        raise SystemExit("Usage: blender_worker.py -- RECIPE PARAMS_JSON OUTPUT_GLB")
    recipe_id, params_path, output_path=args
    if recipe_id not in MODULES:
        raise SystemExit("Unknown recipe: "+recipe_id)
    with open(params_path,encoding="utf-8") as f:
        params=json.load(f)
    clear_scene()
    MODULES[recipe_id].build(params)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active=bpy.context.selected_objects[0]
    bpy.ops.export_scene.gltf(filepath=output_path,export_format="GLB",use_selection=True,export_apply=True)
    print("EXPORTED:"+output_path)

if __name__=="__main__":
    main()
