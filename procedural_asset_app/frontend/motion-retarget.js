const mixamoAliases = {
  hips: 'pelvis',
  spine: 'spine_01', spine1: 'spine_02', spine2: 'spine_03',
  neck: 'neck_01',
  leftshoulder: 'clavicle_l', leftarm: 'upperarm_l', leftforearm: 'lowerarm_l', lefthand: 'hand_l',
  rightshoulder: 'clavicle_r', rightarm: 'upperarm_r', rightforearm: 'lowerarm_r', righthand: 'hand_r',
  leftupleg: 'thigh_l', leftleg: 'calf_l', leftfoot: 'foot_l', lefttoebase: 'ball_l', lefttoeend: 'ball_leaf_l',
  rightupleg: 'thigh_r', rightleg: 'calf_r', rightfoot: 'foot_r', righttoebase: 'ball_r', righttoeend: 'ball_leaf_r'
};

export function normalizedBoneName(name) {
  return name.replace(/^mixamorig[:_]?/i, '').replace(/[^a-z0-9]/gi, '').toLowerCase();
}

export function targetBoneKey(sourceName) {
  const key = normalizedBoneName(sourceName);
  const finger = key.match(/^(left|right)hand(thumb|index|middle|ring|pinky)([1-4])$/);
  if (finger) return `${finger[2]}_0${finger[3]}_${finger[1] === 'left' ? 'l' : 'r'}`;
  return mixamoAliases[key] || key;
}

function worldQuaternion(THREE, node) {
  if (!node) return new THREE.Quaternion();
  node.updateWorldMatrix(true, false);
  return node.getWorldQuaternion(new THREE.Quaternion());
}

/** Convert a Mixamo FBX clip into the target rig's local bind-space tracks. */
export function retargetMixamoClip(THREE, sourceRoot, targetRoot, bindPose, sourceClip) {
  if (!sourceRoot || !targetRoot || !bindPose) throw new Error('A source rig, target rig, and target bind pose are required.');
  sourceRoot.updateMatrixWorld(true);
  targetRoot.updateMatrixWorld(true);
  const sourceBones = new Map(), targetBones = new Map();
  sourceRoot.traverse(node => { if (node.isBone) sourceBones.set(normalizedBoneName(node.name), node); });
  targetRoot.traverse(node => { if (node.isBone) targetBones.set(normalizedBoneName(node.name), node); });
  const tracks = [];

  for (const sourceTrack of sourceClip.tracks) {
    const split = sourceTrack.name.lastIndexOf('.');
    if (split < 0) continue;
    const sourceName = sourceTrack.name.slice(0, split);
    const property = sourceTrack.name.slice(split + 1);
    if (property !== 'quaternion' && property !== 'position') continue;
    const sourceBone = sourceBones.get(normalizedBoneName(sourceName));
    const targetBone = targetBones.get(normalizedBoneName(targetBoneKey(sourceName)));
    const targetRest = targetBone && bindPose.get(targetBone);
    if (!sourceBone || !targetBone || !targetRest) continue;

    // Basis maps source-parent local axes into the target-parent local frame.
    const sourceParentQ = worldQuaternion(THREE, sourceBone.parent);
    const targetParentQ = worldQuaternion(THREE, targetBone.parent);
    const basis = targetParentQ.clone().invert().multiply(sourceParentQ);
    const inverseBasis = basis.clone().invert();

    if (property === 'quaternion') {
      const inverseSourceRest = sourceBone.quaternion.clone().normalize().invert();
      const targetRestQ = targetRest.quaternion.clone().normalize();
      const values = new Float32Array(sourceTrack.values.length);
      let previous = null;
      for (let i = 0; i < sourceTrack.values.length; i += 4) {
        const animated = new THREE.Quaternion(
          sourceTrack.values[i], sourceTrack.values[i + 1], sourceTrack.values[i + 2], sourceTrack.values[i + 3]
        ).normalize();
        const delta = inverseSourceRest.clone().multiply(animated);
        const converted = targetRestQ.clone().multiply(basis).multiply(delta).multiply(inverseBasis).normalize();
        if (previous && previous.dot(converted) < 0) converted.set(-converted.x, -converted.y, -converted.z, -converted.w);
        values.set(converted.toArray(), i);
        previous = converted;
      }
      tracks.push(new THREE.QuaternionKeyframeTrack(
        `${targetBone.name}.quaternion`, sourceTrack.times.slice(), values
      ));
    } else {
      const values = new Float32Array(sourceTrack.values.length);
      const sourceRestPosition = sourceBone.position;
      for (let i = 0; i < sourceTrack.values.length; i += 3) {
        const delta = new THREE.Vector3(
          sourceTrack.values[i] - sourceRestPosition.x,
          sourceTrack.values[i + 1] - sourceRestPosition.y,
          sourceTrack.values[i + 2] - sourceRestPosition.z
        ).applyQuaternion(basis).multiplyScalar(0.01);
        values[i] = targetRest.position.x + delta.x;
        values[i + 1] = targetRest.position.y + delta.y;
        values[i + 2] = targetRest.position.z + delta.z;
      }
      tracks.push(new THREE.VectorKeyframeTrack(
        `${targetBone.name}.position`, sourceTrack.times.slice(), values
      ));
    }
  }

  if (tracks.length < 30) throw new Error(`Only ${tracks.length} bone tracks matched; expected a compatible 65-bone Mixamo motion.`);
  return new THREE.AnimationClip(sourceClip.name, sourceClip.duration, tracks);
}
