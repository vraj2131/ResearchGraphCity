import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  askCityNavigation,
  cancelBuildJob,
  compareCities,
  createCity,
  exportEvidenceReport,
  fetchBuildJob,
  fetchCity,
  fetchResearchCity,
  fetchSeedGraph,
  fetchTimeline,
  queueCityBuild,
} from './api';

describe('fetchResearchCity', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fails the city load when the research streets endpoint is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/buildings')) {
          return Promise.resolve(new Response(JSON.stringify([{ building_id: 'B_R_0001' }])));
        }
        if (url.endsWith('/bridges')) {
          return Promise.resolve(new Response(JSON.stringify([{ bridge_id: 'BR_R_0001_0002' }])));
        }
        if (url.endsWith('/streets')) {
          return Promise.resolve(new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 }));
        }
        if (url.endsWith('/communities')) {
          return Promise.resolve(new Response(JSON.stringify([{ community_id: 'C_R_0001' }])));
        }
        return Promise.resolve(new Response(JSON.stringify([])));
      }),
    );

    await expect(fetchResearchCity()).rejects.toThrow('Request failed: /api/cities/research/streets');
  });

  it('does not derive client layout streets when the API returns no streets', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/buildings')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { building_id: 'B_R_0001', x: 0, z: 0 },
                { building_id: 'B_R_0002', x: 10, z: 0 },
                { building_id: 'B_R_0003', x: 40, z: 0 },
              ]),
            ),
          );
        }
        if (url.endsWith('/bridges')) {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        if (url.endsWith('/streets')) {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        if (url.endsWith('/communities')) {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        return Promise.resolve(new Response(JSON.stringify([])));
      }),
    );

    await expect(fetchResearchCity()).rejects.toThrow('No research streets available');
  });

  it('can fetch a seeded city with the same city payload shape', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/seeded/buildings')) {
          return Promise.resolve(new Response(JSON.stringify([{ building_id: 'B_R_0001' }])));
        }
        if (url.endsWith('/seeded/bridges')) {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        if (url.endsWith('/seeded/streets')) {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        if (url.endsWith('/seeded/communities')) {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        return Promise.resolve(new Response(JSON.stringify([])));
      }),
    );

    await expect(fetchCity('seeded')).resolves.toEqual({
      buildings: [{ building_id: 'B_R_0001' }],
      bridges: [],
      streets: [],
      communities: [],
    });
  });

  it('creates a city from normalized seed inputs at the selected scale', async () => {
    const response = {
      city_id: 'city-1',
      city_type: 'seeded-city-1',
      name: 'My research city',
      status: 'draft',
      target_paper_count: 100000,
      seed_count: 2,
      warnings: ['Removed 1 duplicate seed input.'],
    };
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(response), { status: 201 })));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createCity('My research city', ['Paper A', 'Paper B', 'Paper A'], 100000)).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/cities',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'My research city',
          seed_inputs: ['Paper A', 'Paper B', 'Paper A'],
          target_paper_count: 100000,
        }),
      }),
    );
  });

  it('queues, polls, and cancels a city build job', async () => {
    const queued = {
      job_id: 'job-1', city_id: 'city-1', status: 'queued', stage: 'queued',
      progress_current: 0, progress_total: 100000, message: 'Build queued', cancel_requested: false, error: null,
    };
    const cancelled = { ...queued, status: 'cancelled', cancel_requested: true, message: 'Build cancelled' };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/cities/city-1/build') return Promise.resolve(new Response(JSON.stringify(queued), { status: 202 }));
      if (url === '/api/jobs/job-1/cancel' && init?.method === 'POST') return Promise.resolve(new Response(JSON.stringify(cancelled), { status: 202 }));
      return Promise.resolve(new Response(JSON.stringify(queued)));
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(queueCityBuild('city-1')).resolves.toEqual(queued);
    await expect(fetchBuildJob('job-1')).resolves.toEqual(queued);
    await expect(cancelBuildJob('job-1')).resolves.toEqual(cancelled);
    expect(fetchMock).toHaveBeenCalledWith('/api/cities/city-1/build', expect.objectContaining({ method: 'POST' }));
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs/job-1');
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs/job-1/cancel', expect.objectContaining({ method: 'POST' }));
  });

  it('posts research questions to the active city assistant', async () => {
    const response = {
      answer_markdown: 'Inspect B_R_0001.',
      claims: [],
      papers: [],
      buildings: [],
      districts: [],
      relationships: [],
      route_steps: [{ label: 'Graph methods', target_type: 'building', target_id: 'B_R_0001', reason: 'Best match' }],
      filters_applied: {},
      retrieval_summary: {},
      confidence: 0.8,
      model_available: true,
    };
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(response))));
    vi.stubGlobal('fetch', fetchMock);

    await expect(askCityNavigation('seeded', 'Where is graph work?')).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/cities/seeded/assistant/query',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: 'Where is graph work?', filters: {}, limit: 12 }),
      }),
    );
  });

  it('loads seed context and analysis artifacts from bounded endpoints', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('/seed-graph')) return Promise.resolve(new Response(JSON.stringify({ nodes: [], edges: [], unresolved: [], warnings: [] })));
      if (url.endsWith('/timeline')) return Promise.resolve(new Response(JSON.stringify({ city_id: 'research', years: [] })));
      if (url.endsWith('/exports/evidence-report')) return Promise.resolve(new Response('# Evidence'));
      return Promise.resolve(new Response(JSON.stringify({ papers: { shared: 4 } })));
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchSeedGraph('city-1')).resolves.toMatchObject({ nodes: [] });
    await expect(fetchTimeline('research')).resolves.toMatchObject({ city_id: 'research' });
    await expect(compareCities('research', 'seeded')).resolves.toMatchObject({ papers: { shared: 4 } });
    await expect(exportEvidenceReport('research', 'graph papers', { open_access: true })).resolves.toBe('# Evidence');

    expect(fetchMock).toHaveBeenCalledWith('/api/cities/compare', expect.objectContaining({ method: 'POST' }));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/cities/research/exports/evidence-report',
      expect.objectContaining({ body: JSON.stringify({ question: 'graph papers', filters: { open_access: true }, limit: 20 }) }),
    );
  });
});
