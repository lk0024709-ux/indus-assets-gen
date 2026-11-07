# 3D Asset Viewer

Open `asset-viewer.html` from the procedural asset app. It opens with the repository's superhero models ready to inspect; choose Female/Male and Dark/Light from the built-in character selector, or open/drop a local model.

**Supported input:** GLB, GLTF, FBX, and OBJ. Use **Open** to choose a file, or drag and drop one onto the viewer.

The viewer provides orbit/zoom, grid, spin, wireframe, skeleton visualization, animation clip playback, timeline scrubbing, and GLB/FBX motion retargeting for compatible skeletons. The bundled character GLBs have a 65-joint rig but no embedded animation clips. Open **Character Studio** from the viewer card to choose and play all 74 repository motions on the superhero rig.

The page uses Three.js 0.128 from jsDelivr. A network connection is needed in the browser for those viewer libraries. Built-in character files are loaded from `assets/characters/`; local user-selected files stay in the browser and are not uploaded to a server.
