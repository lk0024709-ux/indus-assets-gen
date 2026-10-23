import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const $ = id => document.getElementById(id);
const select=$('recipeSelect'), form=$('paramsForm'), fields=$('paramFields');
let recipes=[], currentRecipe=null, currentParams={}, currentUrl=null, renderer, scene, camera, controls, currentModel=null;
const defaults={};
async function api(url,options={}){const response=await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||('Request failed ('+response.status+')'));return data}
function setMessage(text,error=false){$('message').textContent=text;$('message').classList.toggle('error',error)}
function initViewer(){
 const host=$('viewport');scene=new THREE.Scene();scene.background=new THREE.Color('#10151f');
 camera=new THREE.PerspectiveCamera(42,host.clientWidth/host.clientHeight,.1,100);camera.position.set(4,3,5);
 renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.1;host.prepend(renderer.domElement);
 const pmrem=new THREE.PMREMGenerator(renderer);scene.environment=pmrem.fromScene(new RoomEnvironment(),.04).texture;pmrem.dispose();
 scene.add(new THREE.HemisphereLight(0xdce8ff,0x41404a,2));
 const key=new THREE.DirectionalLight(0xffedcf,3);key.position.set(4,7,5);scene.add(key);
 const fill=new THREE.DirectionalLight(0x8baeff,1.5);fill.position.set(-5,3,-3);scene.add(fill);
 const grid=new THREE.GridHelper(12,24,0x3d4a5c,0x263140);grid.position.y=-.015;scene.add(grid);
 const ground=new THREE.Mesh(new THREE.CircleGeometry(6,64),new THREE.MeshStandardMaterial({color:0x111722,roughness:.9}));ground.rotation.x=-Math.PI/2;ground.position.y=-.025;scene.add(ground);
 controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,.7,0);
 const resize=()=>{const w=host.clientWidth,h=host.clientHeight;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false)};new ResizeObserver(resize).observe(host);resize();
 const animate=()=>{requestAnimationFrame(animate);controls.update();renderer.render(scene,camera)};animate();
}
function frameModel(model){
 const box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
 model.position.sub(center);const max=Math.max(size.x,size.y,size.z)||1;camera.position.set(max*1.9,max*1.25,max*2.1);camera.near=Math.max(.01,max/100);camera.far=max*100;camera.updateProjectionMatrix();controls.target.set(0,0,0);controls.update();
}
function showModel(url){
 $('loader').classList.remove('hidden');$('emptyState').classList.add('hidden');
 new GLTFLoader().load(url+(url.includes('?')?'&':'?')+'t='+Date.now(),gltf=>{
  if(currentModel)scene.remove(currentModel);currentModel=gltf.scene;scene.add(currentModel);frameModel(currentModel);$('loader').classList.add('hidden');$('assetStatus').textContent='Model loaded successfully';$('download').disabled=false;
 },undefined,error=>{console.error(error);$('loader').classList.add('hidden');$('emptyState').classList.remove('hidden');setMessage('Could not load the exported GLB in the viewport.',true)});
}
function buildFields(recipe){
 fields.innerHTML='';currentRecipe=recipe;currentParams={};
 $('recipeDescription').textContent=recipe.description;
 for(const [key,spec] of Object.entries(recipe.parameters)){
  let value=spec.default;if(spec.type==='enum'&&key==='leg_count')value=String(value);currentParams[key]=value;
  const wrap=document.createElement('div');wrap.className='parameter';
  const head=document.createElement('div');head.className='parameter-head';
  const label=document.createElement('label');label.htmlFor='p_'+key;label.textContent=spec.label;
  const output=document.createElement('output');output.id='out_'+key;output.textContent=String(value);
  head.append(label,output);wrap.append(head);let input;
  if(spec.type==='enum'){input=document.createElement('select');for(const option of spec.options){const o=document.createElement('option');o.value=option;o.textContent=option;input.append(o)}input.value=String(value)}
  else if(spec.type==='bool'){input=document.createElement('input');input.type='checkbox';input.checked=Boolean(value)}
  else if(spec.type==='color'){input=document.createElement('input');input.type='color';input.value=value}
  else{input=document.createElement('input');input.type='range';input.min=spec.min;input.max=spec.max;input.step=spec.step||1;input.value=value}
  input.id='p_'+key;input.addEventListener('input',()=>{let v=spec.type==='bool'?input.checked:input.value;if(spec.type==='int')v=parseInt(v,10);if(spec.type==='float')v=parseFloat(v);currentParams[key]=v;output.textContent=String(v)});wrap.append(input);fields.append(wrap);
 }
}
async function loadRecipes(){recipes=await api('/api/recipes');select.innerHTML='';for(const r of recipes){const o=document.createElement('option');o.value=r.id;o.textContent=r.name;select.append(o)}buildFields(recipes[0])}
select.addEventListener('change',()=>buildFields(recipes.find(r=>r.id===select.value)));
form.addEventListener('submit',async event=>{event.preventDefault();$('download').disabled=true;$('loader').classList.remove('hidden');$('emptyState').classList.add('hidden');$('assetStatus').textContent='Generating…';setMessage('Blender is building your asset…');try{const result=await api('/api/generate',{method:'POST',body:JSON.stringify({recipe:currentRecipe.id,params:currentParams})});currentUrl=result.url;$('cacheKey').textContent=result.hash;$('generationMode').textContent=result.cached?'Cached output':'Fresh build';$('assetStatus').textContent=result.cached?'Loaded from cache':'Generation complete';setMessage(result.cached?'Loaded cached asset.':'Asset generated and exported as GLB.');showModel(result.url)}catch(err){$('loader').classList.add('hidden');$('emptyState').classList.remove('hidden');$('assetStatus').textContent='Generation failed';setMessage(err.message,true)}});
$('randomize').addEventListener('click',()=>{for(const [key,spec] of Object.entries(currentRecipe.parameters)){const input=$('p_'+key);let v;if(spec.type==='enum')v=spec.options[Math.floor(Math.random()*spec.options.length)];else if(spec.type==='bool')v=Math.random()>.5;else if(spec.type==='color')v='#'+Math.floor(Math.random()*0xffffff).toString(16).padStart(6,'0');else{const step=spec.step||1;const count=Math.floor((spec.max-spec.min)/step);v=spec.min+Math.floor(Math.random()*(count+1))*step;if(spec.type==='int')v=Math.round(v);else v=Number(v.toFixed(3))}if(spec.type==='bool')input.checked=v;else input.value=String(v);currentParams[key]=v;$('out_'+key).textContent=String(v)}setMessage('Parameters randomized. Generate to build this variation.')});
$('download').addEventListener('click',()=>{if(!currentUrl)return;const a=document.createElement('a');a.href=currentUrl;a.download=currentUrl.split('/').pop();document.body.append(a);a.click();a.remove()});
$('resetView').addEventListener('click',()=>{if(currentModel)frameModel(currentModel);else{camera.position.set(4,3,5);controls.target.set(0,.7,0);controls.update()}});
async function start(){initViewer();try{const h=await api('/api/health');$('healthDot').classList.add(h.blender_configured?'ok':'bad');$('healthText').textContent=h.blender_configured?'Blender ready':'Blender not found';if(!h.blender_configured)setMessage('API is online, but Blender is not installed/configured on the backend.',true);await loadRecipes()}catch(err){$('healthDot').classList.add('bad');$('healthText').textContent='API unavailable';setMessage('Cannot reach backend: '+err.message,true)}}
start();
