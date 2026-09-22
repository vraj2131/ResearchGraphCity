import { describe, expect, it } from 'vitest';

import { bridgeOpacity, bridgeWidth, buildingMaterial, communityColor, floorHeight, floorMaterial, selectedHighlight } from './visualMapping';
import type { Building, Bridge, Floor } from './types';

const building: Building = {
  building_id: 'B_R_0001',
  city_type: 'research',
  vertex_ids: ['R_1'],
  node_count: 100,
  edge_count: 200,
  internal_density: 0.4,
  avg_core: 12,
  max_core: 20,
  height: 80,
  footprint: 24,
  x: 0,
  z: 0,
  top_labels: ['graph visualization'],
  semantic_domain: 'graph_ai',
  semantic_domain_name: 'Graph, AI, and Computation',
  semantic_color: '#6ee7f9',
  profile: {},
  activation: { score: 0.7 },
  activation_score: 0.7,
  floors: [],
  summary: null,
  community_id: 'C_R_0001',
};

const bridge: Bridge = {
  bridge_id: 'BR_R_0001_0002',
  city_type: 'research',
  source_building_id: 'B_R_0001',
  target_building_id: 'B_R_0002',
  bridge_strength: 0.6,
  bridge_type: 'semantic_structural',
  components: {},
  evidence: [],
  summary: null,
  activation_score: 0.4,
};

describe('visual mapping', () => {
  it('maps bridge strength to width and opacity', () => {
    expect(bridgeWidth(bridge)).toBe(7);
    expect(bridgeOpacity(bridge)).toBe(0.7);
  });

  it('uses semantic community for color and activation only for emissive intensity', () => {
    const material = buildingMaterial(building, { C_R_0001: '#4f8cff' });
    expect(material.color).toBe('#6ee7f9');
    expect(material.emissiveIntensity).toBe(0.7);
  });

  it('uses deterministic fallback community colors', () => {
    expect(communityColor('C_R_0001')).toMatch(/^#[0-9a-f]{6}$/);
    expect(communityColor('C_R_0001')).toBe(communityColor('C_R_0001'));
  });

  it('splits building height evenly by number of floors', () => {
    expect(floorHeight({ ...building, floors: [{ floor_id: 'F1' } as never, { floor_id: 'F2' } as never] })).toBe(40);
  });

  it('darkens floor color as floor activation increases', () => {
    const lowFloor = { floor_id: 'F1', activation_score: 0.1 } as Floor;
    const highFloor = { floor_id: 'F2', activation_score: 0.95 } as Floor;

    const low = floorMaterial(building, lowFloor, 0, 2, {});
    const high = floorMaterial(building, highFloor, 1, 2, {});

    expect(high.color).not.toBe(low.color);
    expect(luminance(high.color)).toBeLessThan(luminance(low.color));
  });

  it('uses a high-contrast amber selection highlight', () => {
    expect(selectedHighlight.color).toBe('#f59e0b');
    expect(selectedHighlight.emissiveIntensity).toBeGreaterThan(0.8);
  });
});

function luminance(color: string) {
  const hex = color.replace('#', '');
  const red = Number.parseInt(hex.slice(0, 2), 16);
  const green = Number.parseInt(hex.slice(2, 4), 16);
  const blue = Number.parseInt(hex.slice(4, 6), 16);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}
