from recipes import chair, table, lamp, rock, barrel

RECIPES = {
    "chair": chair,
    "table": table,
    "lamp": lamp,
    "rock": rock,
    "barrel": barrel,
}

def public_recipes():
    return [{"id": key, "name": mod.NAME, "description": mod.DESCRIPTION,
             "parameters": mod.PARAMETERS} for key, mod in RECIPES.items()]

def validate_params(recipe_id: str, incoming: dict) -> dict:
    if recipe_id not in RECIPES:
        raise ValueError("Unknown recipe")
    schema = RECIPES[recipe_id].PARAMETERS
    result = {}
    for key, spec in schema.items():
        value = incoming.get(key, spec["default"])
        kind = spec["type"]
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                raise ValueError(f"{key} must be an integer")
            value = int(value)
        elif kind == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            value = float(value)
        elif kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
        elif kind == "enum":
            if value not in spec["options"]:
                raise ValueError(f"{key} must be one of {', '.join(spec['options'])}")
        elif kind == "color":
            if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
                raise ValueError(f"{key} must be a hex color")
            try:
                int(value[1:], 16)
            except ValueError as exc:
                raise ValueError(f"{key} must be a hex color") from exc
        if "min" in spec and value < spec["min"]:
            raise ValueError(f"{key} must be at least {spec['min']}")
        if "max" in spec and value > spec["max"]:
            raise ValueError(f"{key} must be at most {spec['max']}")
        result[key] = value
    return result
