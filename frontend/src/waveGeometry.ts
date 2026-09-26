import type { Floor } from './types';

export interface WaveGeometry {
  bottom: number;
  height: number;
  lower_radius: number;
  upper_radius: number;
}

export function floorGeometry(floor: Floor): WaveGeometry | null {
  const summary = floor.summary as { geometry?: WaveGeometry } | null;
  const geometry = summary?.geometry;
  if (!geometry || !Object.values(geometry).every(Number.isFinite)) return null;
  return geometry;
}

/** Interpolate across omitted preview waves; exact for consecutive waves. */
export function waveSegments(floors: Floor[]): (WaveGeometry & { floor_id: string })[] {
  const samples = floors.flatMap(floor => {
    const geometry = floorGeometry(floor);
    return geometry ? [{ floor_id: floor.floor_id, ...geometry }] : [];
  });
  return samples.map((sample, index) => {
    const next = samples[index + 1];
    if (next && next.bottom > sample.bottom + sample.height + 1e-8) {
      return { ...sample, height: next.bottom - sample.bottom, upper_radius: next.lower_radius };
    }
    return sample;
  });
}
