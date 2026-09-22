import { describe, expect, it } from 'vitest';
import * as THREE from 'three';

import { fitInteriorCamera } from './interiorCamera';

describe('fitInteriorCamera', () => {
  it('moves the camera so the interior bounds stay in front of the view target', () => {
    const camera = new THREE.PerspectiveCamera(48, 16 / 9, 0.1, 1000);
    camera.position.set(0, 90, 160);
    const controls = {
      target: new THREE.Vector3(0, 40, 0),
      update() {},
      minDistance: 45,
      maxDistance: 520,
    };
    const positions = [
      { paperId: 'a', x: -40, y: 8, z: -40, floorIndex: 1 },
      { paperId: 'b', x: 40, y: 8, z: 40, floorIndex: 1 },
      { paperId: 'c', x: 0, y: 96, z: 0, floorIndex: 4 },
    ];

    fitInteriorCamera(camera, controls, positions, { minDistance: 45, maxDistance: 520 });

    expect(controls.target.y).toBeGreaterThan(20);
    expect(camera.position.y).toBeGreaterThan(controls.target.y);
    expect(camera.position.distanceTo(controls.target)).toBeGreaterThan(45);
    expect(camera.position.distanceTo(controls.target)).toBeLessThanOrEqual(520);
  });
});
