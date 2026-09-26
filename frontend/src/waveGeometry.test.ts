import { expect, it } from 'vitest';
import { waveSegments } from './waveGeometry';

it('uses original frustum dimensions and spans omitted preview floors', () => {
  const segments = waveSegments([
    { floor_id: 'one', summary: { geometry: { bottom: 0, height: 2, lower_radius: 3, upper_radius: 2 } } },
    { floor_id: 'last', summary: { geometry: { bottom: 10, height: 1, lower_radius: 1, upper_radius: 0 } } },
  ]);
  expect(segments).toEqual([
    { floor_id: 'one', bottom: 0, height: 10, lower_radius: 3, upper_radius: 1 },
    { floor_id: 'last', bottom: 10, height: 1, lower_radius: 1, upper_radius: 0 },
  ]);
});

it('keeps adjacent complete wave geometry exact', () => {
  expect(waveSegments([{ floor_id: 'one', summary: { geometry: { bottom: 0, height: 2, lower_radius: 3, upper_radius: 2 } } }])[0].upper_radius).toBe(2);
  expect(waveSegments([{floor_id: 'legacy'}])).toEqual([]);
});
