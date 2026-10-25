// Read joint names, parentage, and rest transforms from the actual exported GLB.
// No hand-maintained bone map or dependency on model-viewer's private internals.
const tree = document.querySelector('#rig-tree');
const count = document.querySelector('#rig-count');
const toggle = document.querySelector('#joint-toggle');
let markers = [];

const identity = () => [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
function multiply(a,b) {
  const out = new Array(16).fill(0);
  for (let c=0;c<4;c++) for (let r=0;r<4;r++) for (let k=0;k<4;k++) out[c*4+r] += a[k*4+r]*b[c*4+k];
  return out;
}
function localMatrix(node) {
  if (node.matrix) return node.matrix;
  const [x,y,z,w] = node.rotation || [0,0,0,1];
  const [sx,sy,sz] = node.scale || [1,1,1];
  const [tx,ty,tz] = node.translation || [0,0,0];
  return [
    (1-2*(y*y+z*z))*sx, 2*(x*y+z*w)*sx, 2*(x*z-y*w)*sx, 0,
    2*(x*y-z*w)*sy, (1-2*(x*x+z*z))*sy, 2*(y*z+x*w)*sy, 0,
    2*(x*z+y*w)*sz, 2*(y*z-x*w)*sz, (1-2*(x*x+y*y))*sz, 0,
    tx,ty,tz,1,
  ];
}
export function clearRig() {
  for (const marker of markers) marker.remove();
  markers = [];
  tree.replaceChildren();
  count.textContent = 'Loading…';
  toggle.disabled = true;
}
toggle.addEventListener('change', () => {
  for (const marker of markers) marker.hidden = !toggle.checked;
});
export async function loadRig(viewer, url, signal, allowPivots) {
  clearRig();
  const response = await fetch(url, {signal});
  if (!response.ok) throw new Error(`GLB request failed: ${response.status}`);
  const buffer = await response.arrayBuffer();
  if (signal.aborted) return;
  const view = new DataView(buffer);
  if (view.getUint32(0,true) !== 0x46546c67 || view.getUint32(16,true) !== 0x4e4f534a) throw new Error('Invalid GLB JSON chunk');
  const doc = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,view.getUint32(12,true))));
  const joints = new Set((doc.skins || []).flatMap(skin => skin.joints));
  const parents = new Map();
  doc.nodes.forEach((node,index) => (node.children || []).forEach(child => parents.set(child,index)));
  const world = new Map();
  function matrix(index) {
    if (!world.has(index)) world.set(index,multiply(parents.has(index) ? matrix(parents.get(index)) : identity(),localMatrix(doc.nodes[index])));
    return world.get(index);
  }
  const jointParent = new Map();
  for (const joint of joints) {
    let p = parents.get(joint);
    while (p !== undefined && !joints.has(p)) p = parents.get(p);
    jointParent.set(joint,p);
  }
  const children = new Map();
  for (const joint of joints) {
    const p = jointParent.get(joint);
    if (!children.has(p)) children.set(p,[]);
    children.get(p).push(joint);
  }
  function branch(index) {
    const li = document.createElement('li');
    const name = doc.nodes[index].name || `Joint ${index}`;
    const code = document.createElement('code');
    code.textContent = name;
    code.dataset.bone = name;
    code.title = `Parent: ${jointParent.get(index) === undefined ? '(root)' : doc.nodes[jointParent.get(index)].name}`;
    li.append(code);
    if (children.has(index)) {
      const ul = document.createElement('ul');
      for (const child of children.get(index)) ul.append(branch(child));
      li.append(ul);
    }
    if (allowPivots) {
      const m = matrix(index);
      const marker = document.createElement('button');
      marker.type = 'button';
      marker.className = 'joint-marker';
      marker.slot = `hotspot-joint-${index}`;
      marker.dataset.position = `${m[12]}m ${m[13]}m ${m[14]}m`;
      marker.dataset.normal = '0 0 1';
      marker.setAttribute('aria-label',name);
      marker.title = name;
      marker.hidden = !toggle.checked;
      viewer.append(marker);
      markers.push(marker);
    }
    return li;
  }
  for (const root of children.get(undefined) || []) tree.append(branch(root));
  count.textContent = `${joints.size} exported joints`;
  toggle.disabled = !allowPivots;
}
