import * as THREE from 'three';

import type { InteriorNodePosition } from './interiorLayout';

const _box = new THREE.Box3();
const _center = new THREE.Vector3();
const _size = new THREE.Vector3();
const _direction = new THREE.Vector3();

/** Frame the interior camera so every paper node fits in view with padding. */
export function fitInteriorCamera(
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update: () => void; minDistance?: number; maxDistance?: number },
  positions: InteriorNodePosition[],
  options?: { padding?: number; minDistance?: number; maxDistance?: number },
) {
  if (!positions.length) return;

  const padding = options?.padding ?? 14;
  const minDistance = options?.minDistance ?? 50;
  const maxDistance = options?.maxDistance ?? 480;

  _box.makeEmpty();
  for (const node of positions) {
    _box.expandByPoint(new THREE.Vector3(node.x, node.y, node.z));
  }
  if (_box.isEmpty()) return;
  _box.expandByScalar(padding);
  _box.getCenter(_center);
  _box.getSize(_size);

  const fov = THREE.MathUtils.degToRad(camera.fov);
  const aspect = Math.max(0.1, camera.aspect || 1);
  const fitHeight = _size.y > 0 ? _size.y / 2 / Math.tan(fov / 2) : 0;
  const fitWidth = _size.x > 0 ? _size.x / 2 / (Math.tan(fov / 2) * aspect) : 0;
  const fitDepth = _size.z > 0 ? _size.z / 2 / (Math.tan(fov / 2) * aspect) : 0;
  const distance = THREE.MathUtils.clamp(Math.max(fitHeight, fitWidth, fitDepth) * 1.4, minDistance, maxDistance);

  // Oblique view from above/front so floors read clearly without clipping the top.
  _direction.set(0.25, 0.72, 1).normalize();
  camera.position.copy(_center).addScaledVector(_direction, distance);
  camera.near = 0.5;
  camera.far = Math.max(1200, distance * 5);
  camera.updateProjectionMatrix();

  controls.target.copy(_center);
  if (typeof controls.minDistance === 'number') controls.minDistance = minDistance;
  if (typeof controls.maxDistance === 'number') controls.maxDistance = maxDistance;
  controls.update();
}
