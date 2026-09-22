import type {
  Bridge,
  BuildJobResponse,
  Building,
  CityLifecycleResponse,
  CityComparisonResponse,
  CitySummary,
  CityNavigationResponse,
  CityType,
  Community,
  ResearchEdgeDetail,
  ResearchPaper,
  SeedGraphResponse,
  SeededCityResponse,
  Street,
  TimelineResponse,
} from './types';

const json = async <T,>(path: string): Promise<T> => {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`);
  }
  return response.json() as Promise<T>;
};

const requestJson = async <T,>(path: string, init: RequestInit): Promise<T> => {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `Request failed: ${path}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Use the request path when the server did not return a JSON error.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
};

export const fetchResearchCity = async () => {
  return fetchCity('research');
};

export const fetchCities = () => json<CitySummary[]>('/api/cities');

export const fetchTimeline = (cityType: CityType) =>
  json<TimelineResponse>(`/api/cities/${encodeURIComponent(cityType)}/timeline`);

export const compareCities = (leftCityId: CityType, rightCityId: CityType) =>
  requestJson<CityComparisonResponse>('/api/cities/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ left_city_id: leftCityId, right_city_id: rightCityId }),
  });

export const fetchCity = async (cityType: CityType = 'research') => {
  const [buildings, bridges, streets, communities] = await Promise.all([
    json<Building[]>(`/api/cities/${cityType}/buildings`),
    json<Bridge[]>(`/api/cities/${cityType}/bridges`),
    json<Street[]>(`/api/cities/${cityType}/streets`),
    json<Community[]>(`/api/cities/${cityType}/communities`),
  ]);
  if (cityType === 'research' && buildings.length > 1 && streets.length === 0) {
    throw new Error('No research streets available');
  }
  return { buildings, bridges, streets, communities };
};

export const buildSeededCity = async (seedText: string, targetTotal = 1000, perQuery = 100) => {
  const response = await fetch('/api/cities/seeded/build', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seed_text: seedText, target_total: targetTotal, per_query: perQuery }),
  });
  if (!response.ok) {
    let message = 'Seeded city build failed';
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep the generic message when the server does not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<SeededCityResponse>;
};

export const createCity = (name: string, seedInputs: string[], targetPaperCount: number) =>
  requestJson<CityLifecycleResponse>('/api/cities', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, seed_inputs: seedInputs, target_paper_count: targetPaperCount }),
  });

export const queueCityBuild = (cityId: string) =>
  requestJson<BuildJobResponse>(`/api/cities/${encodeURIComponent(cityId)}/build`, { method: 'POST' });

export const fetchBuildJob = (jobId: string) => json<BuildJobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`);

export const cancelBuildJob = (jobId: string) =>
  requestJson<BuildJobResponse>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });

export const fetchSeedGraph = (cityId: string) =>
  json<SeedGraphResponse>(`/api/cities/${encodeURIComponent(cityId)}/seed-graph`);

export const askCityNavigation = async (cityType: CityType, question: string, filters: Record<string, unknown> = {}) => {
  const response = await fetch(`/api/cities/${encodeURIComponent(cityType)}/assistant/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, filters, limit: 12 }),
  });
  if (!response.ok) {
    let message = 'Research assistant failed';
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep the generic message when the server does not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<CityNavigationResponse>;
};

export const exportEvidenceReport = async (cityType: CityType, question: string, filters: Record<string, unknown> = {}) => {
  const response = await fetch(`/api/cities/${encodeURIComponent(cityType)}/exports/evidence-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, filters, limit: 20 }),
  });
  if (!response.ok) throw new Error('Evidence report export failed');
  return response.text();
};

const floorQuery = (floorId: string | null) => (floorId ? `?floor_id=${encodeURIComponent(floorId)}` : '');

export const fetchBuildingPapers = async (cityType: CityType, buildingId: string, floorId: string | null = null) =>
  json<ResearchPaper[]>(`/api/cities/${cityType}/building/${buildingId}/papers${floorQuery(floorId)}`);

export const fetchBuildingEdges = async (cityType: CityType, buildingId: string, floorId: string | null = null) =>
  json<ResearchEdgeDetail[]>(`/api/cities/${cityType}/building/${buildingId}/edges${floorQuery(floorId)}`);

export const fetchBridgeCrossEdges = async (cityType: CityType, bridgeId: string) =>
  json<ResearchEdgeDetail[]>(`/api/cities/${cityType}/bridge/${bridgeId}/edges`);
