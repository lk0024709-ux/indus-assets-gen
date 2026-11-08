# 3D Asset Viewer

Open `asset-viewer.html` from the procedural asset app. It opens with the repository's superhero models equipped with the fitted **Battle Royale tactical outfit** ready to inspect; choose outfitted heroes, base superhero rigs, or standalone/fitted Battle Royale outfits from the built-in selector, or open/drop a local model.

**Supported input:** GLB, GLTF, FBX, and OBJ. Use **Open** to choose a file, or drag and drop one onto the viewer.

The viewer provides orbit/zoom, grid, spin, wireframe, skeleton visualization, animation clip playback, timeline scrubbing, and GLB/FBX motion retargeting for compatible skeletons. Open **Character Studio** (`characters.html`) from the viewer card to toggle modular Battle Royale outfit layers, play all 74 repository motions, and export combined hero + outfit GLBs.

The page uses Three.js 0.128 from jsDelivr. Built-in character and outfit files are loaded from `assets/characters/` and `assets/outfits/`; local user-selected files stay in the browser and are not uploaded to a server.
