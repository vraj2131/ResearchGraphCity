export type CityType = string;

export interface Floor {
  floor_id: string;
  building_id?: string;
  floor_index?: number;
  core_range?: [number, number];
  vertex_ids?: string[];
  node_count?: number;
  top_labels?: string[];
  activation_score?: number;
  summary?: unknown;
}

export interface Building {
  building_id: string;
  city_type: CityType;
  vertex_ids: string[];
  node_count: number;
  edge_count: number;
  internal_density: number;
  avg_core: number;
  max_core: number;
  height: number;
  footprint: number;
  x: number;
  z: number;
  top_labels: string[];
  semantic_domain?: string;
  semantic_domain_name?: string;
  semantic_color?: string;
  profile: Record<string, unknown>;
  original_labels?: Record<string, string[]>;
  activation: Record<string, number>;
  activation_score: number;
  floors: Floor[];
  summary: unknown | null;
  community_id: string | null;
}

export interface Bridge {
  bridge_id: string;
  city_type: CityType;
  source_building_id: string;
  target_building_id: string;
  bridge_strength: number;
  bridge_type: string;
  components: Record<string, number>;
  evidence: string[];
  summary: unknown | null;
  activation_score: number;
}

export interface Street {
  street_id: string;
  city_type: CityType;
  source_building_id: string;
  target_building_id: string;
  street_type: string;
  distance: number;
  street_score: number;
  components: Record<string, number>;
  evidence: string[];
}

export interface ResearchPaper {
  paper_id: string;
  openalex_id?: string;
  doi?: string | null;
  title: string;
  abstract?: string;
  publication_year?: number | null;
  venue?: string;
  topics?: string[];
  keywords?: string[];
  citation_count?: number;
}

export interface EdgePaperRef {
  paper_id: string;
  title?: string;
  publication_year?: number | null;
  venue?: string;
}

export interface ResearchEdgeDetail {
  source: string;
  target: string;
  source_paper?: EdgePaperRef;
  target_paper?: EdgePaperRef;
  edge_type?: string;
  edge_weight: number;
  components?: Record<string, number>;
  evidence?: string[];
  directed_citation?: boolean;
}

export interface Community {
  community_id: string;
  city_type?: CityType;
  name: string;
  building_ids?: string[];
  top_labels?: string[];
  semantic_domain?: string;
  semantic_domain_name?: string;
  metrics?: Record<string, number>;
  summary?: unknown | null;
  color: string;
}

export interface LayerState {
  buildings: boolean;
  bridges: boolean;
  streets: boolean;
  communities: boolean;
  activation: boolean;
  floors: boolean;
  labels: boolean;
  bushes: boolean;
}

export interface InteriorLayerState {
  nodes: boolean;
  edges: boolean;
  labels: boolean;
  floors: boolean;
}

export interface SeededCityResponse {
  city_type: 'seeded';
  counts: Record<string, number>;
  warnings?: string[];
}

export type BuildJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface CityLifecycleResponse {
  city_id: string;
  city_type: string;
  name: string;
  status: string;
  target_paper_count: number;
  seed_count: number;
  warnings: string[];
  provenance?: Record<string, unknown>;
}

export interface BuildJobResponse {
  job_id: string;
  city_id: string;
  status: BuildJobStatus;
  stage: string;
  progress_current: number;
  progress_total: number;
  message: string;
  cancel_requested: boolean;
  error: Record<string, unknown> | null;
}

export interface SeedGraphNode {
  paper_id: string;
  title: string;
  publication_year: number | null;
  venue: string;
  topics: string[];
  seed_position: number | null;
}

export interface SeedGraphResponse {
  city_id: string;
  status: string;
  nodes: SeedGraphNode[];
  edges: Array<{ source: string; target: string; weight: number; directed: boolean }>;
  unresolved: string[];
  warnings: string[];
}

export interface CitySummary {
  city_type: string;
  name: string;
  status?: string;
  city_id?: string;
}

export interface TimelineResponse {
  city_id: string;
  year_min: number | null;
  year_max: number | null;
  years: Array<{
    year: number;
    paper_count: number;
    citation_count: number;
    open_access_count: number;
    building_count: number;
  }>;
}

export interface CityComparisonResponse {
  left_city: { city_id: string; name: string; paper_count: number };
  right_city: { city_id: string; name: string; paper_count: number };
  papers: { shared: number; left_only: number; right_only: number };
  domains: { shared: string[]; left_only: string[]; right_only: string[] };
}

export interface CityNavigationStep {
  label: string;
  target_type: 'building' | 'bridge' | 'street' | 'community' | 'paper';
  target_id: string;
  reason: string;
}

export interface AssistantClaim {
  claim: string;
  citation_ids: string[];
  support_score: number;
}

export interface AssistantPaper extends ResearchPaper {
  evidence_id: string;
  building_id: string | null;
  building_label: string | null;
  district_id: string | null;
  district_name: string | null;
  domain_name: string | null;
  score: number;
}

export interface AssistantEntity {
  evidence_id: string;
  building_id?: string;
  district_id?: string;
  label?: string;
  name?: string;
  domain_name?: string;
}

export interface AssistantRelationship {
  evidence_id: string;
  relationship_id: string;
  relationship_kind: 'bridge' | 'street';
  source_building_id: string;
  target_building_id: string;
  score: number;
  evidence: string[];
}

export interface CityNavigationResponse {
  conversation_id: string | null;
  answer_markdown: string;
  claims: AssistantClaim[];
  papers: AssistantPaper[];
  buildings: AssistantEntity[];
  districts: AssistantEntity[];
  relationships: AssistantRelationship[];
  timeline: Array<{
    evidence_id: string;
    year: number;
    paper_count: number;
    citation_count: number;
    open_access_count: number;
    building_count: number;
  }>;
  route_steps: CityNavigationStep[];
  filters_applied: Record<string, unknown>;
  retrieval_summary: Record<string, unknown>;
  confidence: number;
  model_available: boolean;
}
