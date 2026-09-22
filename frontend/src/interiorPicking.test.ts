import { describe, expect, it } from 'vitest';
import * as THREE from 'three';

import { layoutInteriorNodes } from './interiorLayout';
import { pickInteriorPaperId } from './interiorPicking';
import type { Floor, ResearchPaper } from './types';

describe('pickInteriorPaperId', () => {
  it('selects the node closest on screen, not the nearest along a 3D ray', () => {
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000);
    camera.position.set(0, 40, 160);
    camera.lookAt(0, 40, 0);
    camera.updateMatrixWorld();

    const positions = [
      { paperId: 'upper', x: 20, y: 64, z: 0, floorIndex: 2 },
      { paperId: 'lower', x: -20, y: 36, z: 0, floorIndex: 1 },
    ];

    const size = { width: 800, height: 600 };
    const lowerProjected = new THREE.Vector3(-20, 36, 0).project(camera);
    const pointerX = (lowerProjected.x * 0.5 + 0.5) * size.width;
    const pointerY = (-lowerProjected.y * 0.5 + 0.5) * size.height;

    expect(pickInteriorPaperId(positions, camera, size, pointerX, pointerY, 40)).toBe('lower');
  });

  it('can select a lower-floor node when floors share a near-vertical alignment', () => {
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000);
    camera.position.set(80, 120, 160);
    camera.lookAt(0, 40, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();

    const positions = [
      { paperId: 'upper', x: 30, y: 72, z: 10, floorIndex: 2 },
      { paperId: 'lower', x: 30, y: 40, z: 10, floorIndex: 1 },
    ];
    const size = { width: 900, height: 700 };
    const lowerProjected = new THREE.Vector3(30, 40, 10).project(camera);
    const pointerX = (lowerProjected.x * 0.5 + 0.5) * size.width;
    const pointerY = (-lowerProjected.y * 0.5 + 0.5) * size.height;

    expect(pickInteriorPaperId(positions, camera, size, pointerX, pointerY, 48)).toBe('lower');
  });
});

describe('layoutInteriorNodes', () => {
  it('rotates floors so same-index papers are not stacked in a column', () => {
    const floors: Floor[] = [
      { floor_id: 'F1', floor_index: 1, vertex_ids: ['A1', 'A2'] },
      { floor_id: 'F2', floor_index: 2, vertex_ids: ['B1', 'B2'] },
    ];
    const papers: ResearchPaper[] = [
      { paper_id: 'A1', title: 'A1' },
      { paper_id: 'A2', title: 'A2' },
      { paper_id: 'B1', title: 'B1' },
      { paper_id: 'B2', title: 'B2' },
    ];
    const positions = layoutInteriorNodes(papers, floors);
    const a1 = positions.find((node) => node.paperId === 'A1')!;
    const b1 = positions.find((node) => node.paperId === 'B1')!;
    const angleA = Math.atan2(a1.z, a1.x);
    const angleB = Math.atan2(b1.z, b1.x);
    expect(Math.abs(angleA - angleB)).toBeGreaterThan(0.3);
  });
});
