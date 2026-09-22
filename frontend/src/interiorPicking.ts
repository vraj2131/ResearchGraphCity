import * as THREE from 'three';

import type { InteriorNodePosition } from './interiorLayout';

const _world = new THREE.Vector3();
const _projected = new THREE.Vector3();
const _ndc = new THREE.Vector2();
const _raycaster = new THREE.Raycaster();

export interface PickSize {
  width: number;
  height: number;
}

/**
 * Pick the paper under the cursor.
 * Uses screen proximity first, then distance to the pick ray, so stacked floors
 * and top-down views do not always resolve to the topmost node.
 */
export function pickInteriorPaperId(
  positions: InteriorNodePosition[],
  camera: THREE.Camera,
  size: PickSize,
  pointerX: number,
  pointerY: number,
  maxPixelDistance = 42,
): string | null {
  if (size.width <= 0 || size.height <= 0 || positions.length === 0) return null;

  _ndc.set((pointerX / size.width) * 2 - 1, -(pointerY / size.height) * 2 + 1);
  _raycaster.setFromCamera(_ndc, camera);

  type Candidate = { id: string; screenDist: number; rayDist: number; depth: number };
  const candidates: Candidate[] = [];

  for (const node of positions) {
    _world.set(node.x, node.y, node.z);
    _projected.copy(_world).project(camera);
    if (_projected.z < -1 || _projected.z > 1) continue;

    const screenX = (_projected.x * 0.5 + 0.5) * size.width;
    const screenY = (-_projected.y * 0.5 + 0.5) * size.height;
    const screenDist = Math.hypot(screenX - pointerX, screenY - pointerY);
    const rayDist = _raycaster.ray.distanceToPoint(_world);
    // NDC depth: closer to camera is smaller in typical perspective projection after project().
    const depth = _projected.z;

    // World threshold ~ node radius; screen threshold for easy clicking.
    if (screenDist <= maxPixelDistance || rayDist <= 6) {
      candidates.push({ id: node.paperId, screenDist, rayDist, depth });
    }
  }

  if (candidates.length === 0) return null;

  candidates.sort((left, right) => {
    // Primary: closest on screen to the cursor.
    const screenDelta = left.screenDist - right.screenDist;
    if (Math.abs(screenDelta) > 8) return screenDelta;
    // Near-ties on screen: prefer the node closest to the pick ray in 3D.
    const rayDelta = left.rayDist - right.rayDist;
    if (Math.abs(rayDelta) > 0.75) return rayDelta;
    // Still tied (vertical stack): prefer the deeper node so lower floors stay reachable
    // when the cursor is aimed at the visible lower sphere under a near-aligned upper one.
    return right.depth - left.depth;
  });

  return candidates[0]?.id ?? null;
}
