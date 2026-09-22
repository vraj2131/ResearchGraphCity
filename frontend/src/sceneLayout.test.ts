import { describe, expect, it } from 'vitest';

import { maxLayoutRadius, normalizeCityLayout } from './sceneLayout';
import type { Building } from './types';

const building = (id: string, x: number, z: number): Building => ({
  building_id: id,
  city_type: 'research',
  vertex_ids: [],
  node_count: 10,
  edge_count: 0,
  internal_density: 0,
  avg_core: 0,
  max_core: 0,
  height: 60,
  footprint: 30,
  x,
  z,
  top_labels: [],
  profile: {},
  activation: {},
  activation_score: 0,
  floors: [],
  summary: null,
  community_id: null,
});

describe('scene layout normalization', () => {
  it('recenters and scales wide backend coordinates into the visible city radius', () => {
    const normalized = normalizeCityLayout([
      building('left', -500, -480),
      building('right', 500, 500),
      building('middle', 80, 40),
    ]);

    expect(Math.abs(normalized[0].x + normalized[1].x)).toBeLessThan(1);
    expect(Math.abs(normalized[0].z + normalized[1].z)).toBeLessThan(1);
    expect(maxLayoutRadius(normalized)).toBeLessThanOrEqual(261);
  });
});
