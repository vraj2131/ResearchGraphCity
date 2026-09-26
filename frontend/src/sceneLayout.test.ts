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
  it('fits very tall original buildings and enlarges small original cities uniformly', () => {
    const tall = {...building('tower', 0, 0), height: 10000, quality_metrics: {algorithm: 'graph-cities-v1'}};
    const fitted = normalizeCityLayout([tall])[0];
    expect(fitted.height).toBeLessThanOrEqual(260);
    expect(fitted.footprint / fitted.height).toBeCloseTo(tall.footprint / tall.height);
    const small = normalizeCityLayout([{...tall,height:30,footprint:3}])[0];
    expect(small.height).toBe(260);
    expect(small.footprint).toBe(26);
  });
  it('preserves original geometry proportions when fitting the city', () => {
    const original = [-1000, 1000].map((x, i) => ({
      ...building(String(i), x, 0), quality_metrics: { algorithm: 'graph-cities-v1' },
      floors: [{ floor_id: 'wave', summary: { geometry: { bottom: 2, height: 3, lower_radius: 4, upper_radius: 1 } } }],
    }));
    const scaled = normalizeCityLayout(original);
    const factor = (scaled[1].x - scaled[0].x) / 2000;
    expect(scaled[0].footprint).toBeCloseTo(30 * factor);
    expect(scaled[0].height).toBeCloseTo(60 * factor);
    const summary = scaled[0].floors[0].summary as { geometry: { height: number } };
    expect(summary.geometry.height).toBeCloseTo(3 * factor);
  });
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
