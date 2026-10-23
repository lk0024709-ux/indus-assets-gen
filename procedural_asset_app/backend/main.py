import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from registry import RECIPES, public_recipes, validate_params

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FRONTEND = ROOT / "frontend"
OUT.mkdir(parents=True, exist_ok=True)
BLENDER = os.environ.get("BLENDER_BIN", shutil.which("blender") or "blender")
app = FastAPI(title="Procedural 3D Asset Generator", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class GenerateRequest(BaseModel):
    recipe: str
    params: dict = Field(default_factory=dict)

@app.get("/api/health")
def health():
    return {"status":"ok", "blender_configured": shutil.which(BLENDER) is not None or Path(BLENDER).exists(),
            "blender_path":BLENDER, "recipes":len(RECIPES)}

@app.get("/api/recipes")
def recipes():
    return public_recipes()

@app.post("/api/generate")
def generate(req: GenerateRequest):
    try:
        params=validate_params(req.recipe,req.params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload=json.dumps({"recipe":req.recipe,"params":params},sort_keys=True,separators=(",",":"))
    digest=hashlib.sha256(payload.encode()).hexdigest()[:20]
    filename=f"{req.recipe}_{digest}.glb"
    target=OUT/filename
    if target.exists() and target.stat().st_size > 0:
        return {"url":f"/outputs/{filename}","cached":True,"hash":digest,"params":params}
    if not shutil.which(BLENDER) and not Path(BLENDER).exists():
        raise HTTPException(status_code=503,detail="Blender executable not found. Install Blender 4.x or set BLENDER_BIN.")
    with tempfile.TemporaryDirectory(prefix="assetgen-") as tmp:
        param_file=Path(tmp)/"params.json"
        temp_glb=Path(tmp)/filename
        param_file.write_text(json.dumps(params),encoding="utf-8")
        cmd=[BLENDER,"--background","--factory-startup","--python",str(ROOT/"backend"/"blender_worker.py"),
             "--",req.recipe,str(param_file),str(temp_glb)]
        try:
            run=subprocess.run(cmd,capture_output=True,text=True,timeout=60,check=False)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504,detail="Blender generation exceeded the 60-second timeout.") from exc
        if run.returncode != 0 or not temp_glb.exists() or temp_glb.stat().st_size == 0:
            detail=(run.stderr or run.stdout or "Blender failed without diagnostic output")[-3500:]
            raise HTTPException(status_code=500,detail="Blender export failed: "+detail)
        temp_target=OUT/(filename+".tmp")
        shutil.copyfile(temp_glb,temp_target)
        temp_target.replace(target)
    return {"url":f"/outputs/{filename}","cached":False,"hash":digest,"params":params}

app.mount("/outputs",StaticFiles(directory=OUT),name="outputs")
app.mount("/",StaticFiles(directory=FRONTEND,html=True),name="frontend")
