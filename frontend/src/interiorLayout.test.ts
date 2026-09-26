import { describe, expect, it } from 'vitest';

import { layoutInteriorNodes, strongestInteriorEdges } from './interiorLayout';
import type { Floor, ResearchEdgeDetail, ResearchPaper } from './types';

const floors: Floor[] = [
  { floor_id: 'F1', floor_index: 1, vertex_ids: ['R1', 'R2'] },
  { floor_id: 'F2', floor_index: 2, vertex_ids: ['R3'] },
];

const papers: ResearchPaper[] = [
  { paper_id: 'R1', title: 'One' },
  { paper_id: 'R2', title: 'Two' },
  { paper_id: 'R3', title: 'Three' },
];

describe('interiorLayout', () => {
  it('uses database memberships and keeps distant wave indices within the focused view', () => {
    const located = [
      { paper_id: 'A', title: 'Shared', building_id: 'B2', floor_id: 'F50000', locations: [
        { building_id: 'B1', floor_id: 'F1', floors: [{ floor_id: 'F1', floor_index: 1 }] },
        { building_id: 'B2', floor_id: 'F50000', floors: [{ floor_id: 'F50000', floor_index: 50000 }] },
      ] },
      { paper_id: 'B', title: 'Earlier', building_id: 'B2', floor_id: 'F49900', locations: [
        { building_id: 'B2', floor_id: 'F49900', floors: [{ floor_id: 'F49900', floor_index: 49900 }] },
      ] },
    ];
    const positions = layoutInteriorNodes(located, []);
    expect(positions.find(p => p.paperId === 'A')?.floorIndex).toBe(50000);
    expect(positions.find(p => p.paperId === 'B')?.floorIndex).toBe(49900);
    expect(Math.max(...positions.map(p => p.y))).toBeLessThan(100);
  });

  it('places papers on floor rings with distinct coordinates', () => {
    const positions = layoutInteriorNodes(papers, floors);
    expect(positions).toHaveLength(3);
    expect(positions.find((node) => node.paperId === 'R3')?.floorIndex).toBe(2);
    expect(positions.find((node) => node.paperId === 'R1')?.y).toBeLessThan(positions.find((node) => node.paperId === 'R3')?.y ?? 0);
    const coords = new Set(positions.map((node) => `${node.x},${node.y},${node.z}`));
    expect(coords.size).toBe(3);
  });

  it('keeps only the strongest edges for dense interiors', () => {
    const edges: ResearchEdgeDetail[] = [
      { source: 'R1', target: 'R2', edge_weight: 0.2 },
      { source: 'R1', target: 'R3', edge_weight: 0.9 },
      { source: 'R2', target: 'R3', edge_weight: 0.5 },
    ];
    expect(strongestInteriorEdges(edges, 2).map((edge) => edge.edge_weight)).toEqual([0.9, 0.5]);
  });
});
