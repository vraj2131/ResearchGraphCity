import type { Bridge, Building, Floor } from './types';

const palette = ['#4f8cff', '#ff6b6b', '#42b883', '#f7b801', '#9b5de5', '#00bbf9', '#f15bb5', '#6a994e'];

export const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));

export const bridgeWidth = (bridge: Bridge) => Number((1 + 10 * bridge.bridge_strength).toFixed(3));

export const bridgeOpacity = (bridge: Bridge) => Number((0.25 + 0.75 * bridge.bridge_strength).toFixed(3));

export const selectedHighlight = {
  color: '#f59e0b',
  emissive: '#f59e0b',
  emissiveIntensity: 1.15,
  opacity: 0.82,
};

export const communityColor = (communityId: string | null | undefined) => {
  if (!communityId) return '#8a95a5';
  let hash = 0;
  for (const char of communityId) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return palette[hash % palette.length];
};

export const buildingMaterial = (building: Building, communityColors: Record<string, string>) => {
  const color = building.semantic_color ?? communityColors[building.community_id ?? ''] ?? communityColor(building.community_id);
  return {
    color,
    emissive: color,
    emissiveIntensity: clamp(building.activation_score),
    opacity: 0.35 + 0.65 * clamp(building.activation?.recency ?? building.activation_score),
  };
};

export const floorMaterial = (
  building: Building,
  floor: Pick<Floor, 'activation_score'>,
  index: number,
  totalFloors: number,
  communityColors: Record<string, string>,
) => {
  const base = buildingMaterial(building, communityColors);
  const activation = clamp(floor.activation_score ?? building.activation_score);
  const position = totalFloors <= 1 ? 0 : index / (totalFloors - 1);
  const lowActivationLift = 0.24 * (1 - activation);
  const verticalLift = 0.08 * position;
  const activeDarken = 0.34 * activation;
  const lifted = mixHex(base.color, '#ffffff', lowActivationLift + verticalLift);
  return {
    ...base,
    color: mixHex(lifted, '#0f172a', activeDarken),
    floorActivation: activation,
  };
};

export const floorHeight = (building: Building) => {
  const count = Math.max(1, building.floors.length);
  return Number((building.height / count).toFixed(3));
};

const mixHex = (left: string, right: string, amount: number) => {
  const ratio = clamp(amount);
  const leftRgb = hexToRgb(left);
  const rightRgb = hexToRgb(right);
  return rgbToHex(
    leftRgb[0] + (rightRgb[0] - leftRgb[0]) * ratio,
    leftRgb[1] + (rightRgb[1] - leftRgb[1]) * ratio,
    leftRgb[2] + (rightRgb[2] - leftRgb[2]) * ratio,
  );
};

const hexToRgb = (color: string): [number, number, number] => {
  const clean = color.trim().replace('#', '');
  if (clean.length !== 6) return [148, 163, 184];
  return [Number.parseInt(clean.slice(0, 2), 16), Number.parseInt(clean.slice(2, 4), 16), Number.parseInt(clean.slice(4, 6), 16)];
};

const rgbToHex = (red: number, green: number, blue: number) =>
  `#${[red, green, blue]
    .map((value) => Math.round(Math.min(255, Math.max(0, value))).toString(16).padStart(2, '0'))
    .join('')}`;
