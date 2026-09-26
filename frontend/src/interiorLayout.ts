import type { Floor, ResearchEdgeDetail, ResearchPaper } from './types';

export interface InteriorNodePosition {
  paperId: string;
  x: number;
  y: number;
  z: number;
  floorIndex: number;
}

const FLOOR_SPACING = 22;
const RING_RADIUS = 28;
/** Rotate each floor so papers do not stack in vertical columns (that broke picking). */
const FLOOR_ANGLE_OFFSET = 0.55;

function paperFloorIndex(paper: ResearchPaper, floors: Floor[]): number {
  const location = paper.locations?.find(item => item.building_id === paper.building_id);
  const floorId = paper.floor_id ?? location?.floor_id;
  const knownFloor = [...floors, ...(location?.floors ?? [])].find(floor => floor.floor_id === floorId);
  if (knownFloor) return knownFloor.floor_index ?? 0;
  for (const floor of floors) {
    if (floor.vertex_ids?.includes(paper.paper_id)) {
      return floor.floor_index ?? 0;
    }
  }
  return 0;
}

/** Place papers in rings per floor so the interior graph is readable in 3D. */
export function layoutInteriorNodes(papers: ResearchPaper[], floors: Floor[]): InteriorNodePosition[] {
  const byFloor = new Map<number, ResearchPaper[]>();
  for (const paper of papers) {
    const floorIndex = paperFloorIndex(paper, floors);
    const bucket = byFloor.get(floorIndex) ?? [];
    bucket.push(paper);
    byFloor.set(floorIndex, bucket);
  }

  const positions: InteriorNodePosition[] = [];
  const sortedFloors = [...byFloor.keys()].sort((a, b) => a - b);

  for (const [rank, floorIndex] of sortedFloors.entries()) {
    const floorPapers = byFloor.get(floorIndex) ?? [];
    const count = floorPapers.length;
    // Slightly different radius per floor keeps rings from lining up in the camera view.
    const displayLevel = rank + 1;
    const radius = Math.max(14, RING_RADIUS * Math.sqrt(Math.max(1, count) / 12) + displayLevel * 1.8);
    const angleOffset = displayLevel * FLOOR_ANGLE_OFFSET;
    floorPapers.forEach((paper, index) => {
      const angle = angleOffset + (Math.PI * 2 * index) / Math.max(1, count);
      const jitter = ((index % 5) - 2) * 0.55;
      positions.push({
        paperId: paper.paper_id,
        x: Math.cos(angle) * radius + jitter,
        y: displayLevel * FLOOR_SPACING + 8,
        z: Math.sin(angle) * radius + jitter * 0.6,
        floorIndex,
      });
    });
  }

  return positions;
}

export function strongestInteriorEdges(edges: ResearchEdgeDetail[], limit = 220): ResearchEdgeDetail[] {
  return [...edges].sort((a, b) => b.edge_weight - a.edge_weight).slice(0, limit);
}
