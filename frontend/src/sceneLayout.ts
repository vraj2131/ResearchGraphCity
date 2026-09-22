import type { Building } from './types';

const TARGET_RADIUS = 260;

export function normalizeCityLayout(buildings: Building[]): Building[] {
  if (buildings.length === 0) return buildings;
  const minX = Math.min(...buildings.map((building) => building.x));
  const maxX = Math.max(...buildings.map((building) => building.x));
  const minZ = Math.min(...buildings.map((building) => building.z));
  const maxZ = Math.max(...buildings.map((building) => building.z));
  const centerX = (minX + maxX) / 2;
  const centerZ = (minZ + maxZ) / 2;
  const maxDistance = Math.max(...buildings.map((building) => Math.sqrt((building.x - centerX) ** 2 + (building.z - centerZ) ** 2)));
  const maxFootprintRadius = Math.max(...buildings.map((building) => building.footprint / 2));
  const availableRadius = Math.max(1, TARGET_RADIUS - maxFootprintRadius);
  const scale = maxDistance > availableRadius ? availableRadius / maxDistance : 1;
  return buildings.map((building) => ({
    ...building,
    x: Number(((building.x - centerX) * scale).toFixed(3)),
    z: Number(((building.z - centerZ) * scale).toFixed(3)),
  }));
}

export function maxLayoutRadius(buildings: Building[]) {
  return Math.max(...buildings.map((building) => Math.sqrt(building.x * building.x + building.z * building.z) + building.footprint / 2));
}
