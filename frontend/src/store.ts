import { create } from 'zustand';

import {
  askCityNavigation as requestCityNavigation,
  cancelBuildJob as requestCancelBuildJob,
  createCity,
  fetchBuildJob,
  fetchBuildingEdges,
  fetchBuildingPapers,
  fetchCity,
  fetchSeedGraph,
  queueCityBuild,
} from './api';
import type {
  Bridge,
  BuildJobResponse,
  Building,
  CityNavigationResponse,
  CityType,
  Community,
  InteriorLayerState,
  LayerState,
  ResearchEdgeDetail,
  ResearchPaper,
  SeedGraphResponse,
  Street,
} from './types';

interface CityState {
  cityMode: CityType;
  buildings: Building[];
  bridges: Bridge[];
  streets: Street[];
  communities: Community[];
  selectedBuildingId: string | null;
  selectedBridgeId: string | null;
  selectedStreetId: string | null;
  selectedPaperId: string | null;
  interiorActive: boolean;
  interiorLoading: boolean;
  interiorError: string | null;
  interiorPapers: ResearchPaper[];
  interiorEdges: ResearchEdgeDetail[];
  interiorLayers: InteriorLayerState;
  loading: boolean;
  error: string | null;
  seedBuildStatus: 'idle' | 'creating' | 'queued' | 'building' | 'loaded' | 'cancelled' | 'error';
  seedBuildMessage: string | null;
  seedBuildJob: BuildJobResponse | null;
  seedGraph: SeedGraphResponse | null;
  activeCityId: string | null;
  activeJobId: string | null;
  navigationStatus: 'idle' | 'asking' | 'answered' | 'error';
  navigationError: string | null;
  navigationResponse: CityNavigationResponse | null;
  layers: LayerState;
  loadCity: (cityMode?: CityType) => Promise<void>;
  buildSeededCity: (seedText: string, targetPaperCount?: number) => Promise<void>;
  cancelSeedBuild: () => Promise<void>;
  resumeSeedBuild: () => Promise<void>;
  askCityNavigator: (question: string, filters?: Record<string, unknown>) => Promise<void>;
  selectBuilding: (id: string | null) => void;
  selectBridge: (id: string | null) => void;
  selectStreet: (id: string | null) => void;
  selectPaper: (id: string | null, paper?: ResearchPaper) => void;
  enterBuildingInterior: (buildingId?: string | null) => Promise<void>;
  exitBuildingInterior: () => void;
  toggleLayer: (layer: keyof LayerState) => void;
  toggleInteriorLayer: (layer: keyof InteriorLayerState) => void;
}

const defaultInteriorLayers: InteriorLayerState = {
  nodes: true,
  edges: true,
  labels: true,
  floors: true,
};

const ACTIVE_BUILD_KEY = 'researchGraphCity.activeBuild';
const POLL_INTERVAL_MS = 1000;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

interface PersistedBuild {
  cityId: string;
  cityType: string;
  jobId: string;
}

const uniqueSeedLines = (seedText: string) => {
  const lines = seedText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return lines.filter((line, index) => lines.findIndex((item) => item.toLocaleLowerCase() === line.toLocaleLowerCase()) === index);
};

const clearPollTimer = () => {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
};

const persistBuild = (build: PersistedBuild | null) => {
  if (typeof localStorage === 'undefined') return;
  if (build) localStorage.setItem(ACTIVE_BUILD_KEY, JSON.stringify(build));
  else localStorage.removeItem(ACTIVE_BUILD_KEY);
};

const buildErrorMessage = (job: BuildJobResponse) => {
  const detail = typeof job.error?.message === 'string' ? job.error.message : null;
  return detail ?? job.message ?? 'The city build failed. You can submit it again.';
};

export const useCityStore = create<CityState>((set, get) => ({
  cityMode: 'research',
  buildings: [],
  bridges: [],
  streets: [],
  communities: [],
  selectedBuildingId: null,
  selectedBridgeId: null,
  selectedStreetId: null,
  selectedPaperId: null,
  interiorActive: false,
  interiorLoading: false,
  interiorError: null,
  interiorPapers: [],
  interiorEdges: [],
  interiorLayers: { ...defaultInteriorLayers },
  loading: false,
  error: null,
  seedBuildStatus: 'idle',
  seedBuildMessage: null,
  seedBuildJob: null,
  seedGraph: null,
  activeCityId: null,
  activeJobId: null,
  navigationStatus: 'idle',
  navigationError: null,
  navigationResponse: null,
  layers: {
    buildings: true,
    bridges: true,
    streets: true,
    communities: true,
    activation: true,
    floors: true,
    labels: true,
    bushes: true,
  },
  loadCity: async (cityMode = get().cityMode) => {
    set({
      loading: true,
      error: null,
      selectedBuildingId: null,
      selectedBridgeId: null,
      selectedStreetId: null,
      selectedPaperId: null,
      interiorActive: false,
      interiorPapers: [],
      interiorEdges: [],
      interiorError: null,
      navigationStatus: 'idle',
      navigationError: null,
      navigationResponse: null,
    });
    try {
      const city = await fetchCity(cityMode);
      set({ ...city, cityMode, loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Unable to load city', loading: false });
    }
  },
  buildSeededCity: async (seedText, targetPaperCount = 1000) => {
    const seedInputs = uniqueSeedLines(seedText);
    if (seedInputs.length === 0 || seedInputs.length > 30) {
      set({ seedBuildStatus: 'error', seedBuildMessage: 'Add between 1 and 30 unique paper titles, DOIs, or OpenAlex URLs.' });
      return;
    }
    clearPollTimer();
    set({ seedBuildStatus: 'creating', seedBuildMessage: 'Creating city...', seedBuildJob: null, seedGraph: null, error: null });
    try {
      const city = await createCity('Seeded Research Graph City', seedInputs, targetPaperCount);
      const job = await queueCityBuild(city.city_id);
      const active = { cityId: city.city_id, cityType: city.city_type, jobId: job.job_id };
      persistBuild(active);
      set({
        activeCityId: city.city_id,
        activeJobId: job.job_id,
        seedBuildStatus: job.status === 'running' ? 'building' : 'queued',
        seedBuildMessage: job.message || 'Build queued',
        seedBuildJob: job,
      });
      pollTimer = setTimeout(() => void get().resumeSeedBuild(), POLL_INTERVAL_MS);
    } catch (error) {
      set({
        seedBuildStatus: 'error',
        seedBuildMessage: error instanceof Error ? error.message : 'Unable to build seeded city',
        loading: false,
      });
    }
  },
  resumeSeedBuild: async () => {
    let active: PersistedBuild | null = null;
    if (typeof localStorage !== 'undefined') {
      try {
        active = JSON.parse(localStorage.getItem(ACTIVE_BUILD_KEY) ?? 'null') as PersistedBuild | null;
      } catch {
        persistBuild(null);
      }
    }
    if (!active) return;
    clearPollTimer();
    set({ activeCityId: active.cityId, activeJobId: active.jobId });
    try {
      const job = await fetchBuildJob(active.jobId);
      let seedGraph = get().seedGraph;
      if (job.stage !== 'resolve') {
        try {
          seedGraph = await fetchSeedGraph(active.cityId);
        } catch {
          // Seed preview is supplementary; job polling must continue if it is not ready yet.
        }
      }
      if (job.status === 'succeeded') {
        persistBuild(null);
        set({ seedBuildStatus: 'loaded', seedBuildMessage: job.message || 'Seeded city is ready.', seedBuildJob: job, seedGraph, activeJobId: null });
        await get().loadCity(active.cityType);
        return;
      }
      if (job.status === 'failed') {
        persistBuild(null);
        set({ seedBuildStatus: 'error', seedBuildMessage: buildErrorMessage(job), seedBuildJob: job, activeJobId: null });
        return;
      }
      if (job.status === 'cancelled') {
        persistBuild(null);
        set({ seedBuildStatus: 'cancelled', seedBuildMessage: job.message || 'Build cancelled.', seedBuildJob: job, activeJobId: null });
        return;
      }
      set({
        seedBuildStatus: job.status === 'running' ? 'building' : 'queued',
        seedBuildMessage: job.message,
        seedBuildJob: job,
        seedGraph,
      });
      pollTimer = setTimeout(() => void get().resumeSeedBuild(), POLL_INTERVAL_MS);
    } catch (error) {
      set({
        seedBuildStatus: 'error',
        seedBuildMessage: `${error instanceof Error ? error.message : 'Unable to check build progress'}. Refresh to retry progress tracking.`,
      });
    }
  },
  cancelSeedBuild: async () => {
    const jobId = get().activeJobId;
    if (!jobId) return;
    clearPollTimer();
    try {
      const job = await requestCancelBuildJob(jobId);
      persistBuild(null);
      set({ seedBuildStatus: 'cancelled', seedBuildMessage: job.message || 'Build cancelled.', seedBuildJob: job, activeJobId: null });
    } catch (error) {
      set({ seedBuildStatus: 'error', seedBuildMessage: error instanceof Error ? error.message : 'Unable to cancel build' });
    }
  },
  askCityNavigator: async (question, filters = {}) => {
    const trimmed = question.trim();
    if (!trimmed) return;
    set({ navigationStatus: 'asking', navigationError: null });
    try {
      const response = await requestCityNavigation(get().cityMode, trimmed, filters);
      set({ navigationStatus: 'answered', navigationResponse: response, navigationError: null });
    } catch (error) {
      set({
        navigationStatus: 'error',
        navigationError: error instanceof Error ? error.message : 'Unable to ask city navigator',
      });
    }
  },
  selectBuilding: (id) =>
    set({
      selectedBuildingId: id,
      selectedBridgeId: null,
      selectedStreetId: null,
      selectedPaperId: null,
      ...(get().interiorActive && id !== get().selectedBuildingId
        ? { interiorActive: false, interiorPapers: [], interiorEdges: [], interiorError: null }
        : {}),
    }),
  selectBridge: (id) =>
    set({
      selectedBridgeId: id,
      selectedBuildingId: null,
      selectedStreetId: null,
      selectedPaperId: null,
      interiorActive: false,
      interiorPapers: [],
      interiorEdges: [],
      interiorError: null,
    }),
  selectStreet: (id) =>
    set({
      selectedStreetId: id,
      selectedBuildingId: null,
      selectedBridgeId: null,
      selectedPaperId: null,
      interiorActive: false,
      interiorPapers: [],
      interiorEdges: [],
      interiorError: null,
    }),
  selectPaper: (id, paper) => set(state => ({
    selectedPaperId: id,
    ...(paper && paper.paper_id === id && !state.interiorPapers.some(item => item.paper_id === id)
      ? {interiorPapers: [...state.interiorPapers.slice(0, 199), paper]} : {}),
  })),
  enterBuildingInterior: async (buildingId) => {
    const id = buildingId ?? get().selectedBuildingId;
    if (!id) return;
    const { cityMode } = get();
    set({
      selectedBuildingId: id,
      selectedBridgeId: null,
      selectedStreetId: null,
      selectedPaperId: null,
      interiorActive: true,
      interiorLoading: true,
      interiorError: null,
      interiorPapers: [],
      interiorEdges: [],
    });
    try {
      const [papers, edges] = await Promise.all([fetchBuildingPapers(cityMode, id), fetchBuildingEdges(cityMode, id)]);
      if (get().selectedBuildingId !== id || !get().interiorActive) return;
      set({ interiorPapers: papers, interiorEdges: edges, interiorLoading: false });
    } catch (error) {
      if (get().selectedBuildingId !== id || !get().interiorActive) return;
      set({
        interiorLoading: false,
        interiorError: error instanceof Error ? error.message : 'Unable to load building interior',
      });
    }
  },
  exitBuildingInterior: () =>
    set({
      interiorActive: false,
      interiorLoading: false,
      interiorError: null,
      interiorPapers: [],
      interiorEdges: [],
      selectedPaperId: null,
    }),
  toggleLayer: (layer) => set((state) => ({ layers: { ...state.layers, [layer]: !state.layers[layer] } })),
  toggleInteriorLayer: (layer) =>
    set((state) => ({ interiorLayers: { ...state.interiorLayers, [layer]: !state.interiorLayers[layer] } })),
}));
