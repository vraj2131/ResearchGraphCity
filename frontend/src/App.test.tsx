import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { useCityStore } from './store';

const building = {
  building_id: 'B_R_0001',
  city_type: 'research',
  vertex_ids: ['R_000001', 'R_000002'],
  node_count: 42,
  edge_count: 100,
  internal_density: 0.5,
  avg_core: 8,
  max_core: 12,
  height: 70,
  footprint: 18,
  x: 0,
  z: 0,
  top_labels: ['graph visualization', 'GraphRAG'],
  semantic_domain: 'graph_ai',
  semantic_domain_name: 'Graph, AI, and Computation',
  semantic_color: '#6ee7f9',
  profile: { topics: ['graph visualization'] },
  activation: { score: 0.6 },
  activation_score: 0.6,
  floors: [{ floor_id: 'F_R_0001_01', floor_index: 1, node_count: 1, vertex_ids: ['R_000001'], top_labels: ['graph visualization'] }],
  summary: null,
  community_id: 'C_R_0001',
};

const bridge = {
  bridge_id: 'BR_R_0001_0002',
  city_type: 'research',
  source_building_id: 'B_R_0001',
  target_building_id: 'B_R_0002',
  bridge_strength: 0.7,
  bridge_type: 'semantic_structural',
  components: { semantic_similarity: 0.8 },
  evidence: ['shared_label: graph visualization'],
  summary: null,
  activation_score: 0.5,
};

const street = {
  street_id: 'ST_R_0001_0002',
  city_type: 'research',
  source_building_id: 'B_R_0001',
  target_building_id: 'B_R_0002',
  street_type: 'research_backbone',
  distance: 120,
  street_score: 0.42,
  components: {
    normalized_cross_edge_count: 0.25,
    profile_similarity: 0.5,
    shared_label_similarity: 0.33,
    semantic_similarity: 0.4,
  },
  evidence: ['research_backbone', 'cross_edges: 4'],
};

describe('App', () => {
  beforeEach(() => {
    localStorage.clear();
    useCityStore.setState({
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
      interiorLayers: { nodes: true, edges: true, labels: true, floors: true },
      loading: false,
      error: null,
      seedBuildStatus: 'idle',
      seedBuildMessage: null,
      seedBuildJob: null,
      activeCityId: null,
      activeJobId: null,
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
    });
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === '/api/cities') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                city_id: 'city-1',
                city_type: 'seeded-city-1',
                name: 'Seeded Research Graph City',
                status: 'draft',
                target_paper_count: 100000,
                seed_count: 2,
                warnings: ["Skipped seed 'bad title': no OpenAlex match"],
              }),
              { status: 201 },
            ),
          );
        }
        if (url === '/api/cities/city-1/build') {
          return Promise.resolve(new Response(JSON.stringify({
            job_id: 'job-1', city_id: 'city-1', status: 'queued', stage: 'queued',
            progress_current: 0, progress_total: 100000, message: 'Build queued', cancel_requested: false, error: null,
          }), { status: 202 }));
        }
        if (url === '/api/jobs/job-1') {
          return Promise.resolve(new Response(JSON.stringify({
            job_id: 'job-1', city_id: 'city-1', status: 'running', stage: 'ingestion',
            progress_current: 1200, progress_total: 100000, message: 'Expanding related papers', cancel_requested: false, error: null,
          })));
        }
        if (url === '/api/cities/city-1/seed-graph') {
          return Promise.resolve(new Response(JSON.stringify({
            city_id: 'city-1', status: 'building',
            nodes: [{ paper_id: 'W1', title: 'Resolved Seed Paper', publication_year: 2024, venue: 'Graph Journal', topics: ['Graph'], seed_position: 1 }],
            edges: [], unresolved: ['Unresolved Paper'], warnings: ['One seed did not resolve'],
          })));
        }
        if (url.endsWith('/api/cities/research/assistant/query')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                answer_markdown: 'Start at B_R_0001 for graph visualization.',
                claims: [{ claim: 'Graph visualization is here.', citation_ids: ['paper:W1'], support_score: 0.9 }],
                papers: [{
                  evidence_id: 'paper:W1', paper_id: 'R_000001', openalex_id: 'W1', title: 'Paper One',
                  publication_year: 2025, venue: 'Graph Journal', citation_count: 12, topics: ['graph visualization'],
                  building_id: 'B_R_0001', building_label: 'Graph Visualization', district_id: 'C_R_0001',
                  district_name: 'Graph Research', domain_name: 'Graph, AI, and Computation', score: 0.9,
                }],
                buildings: [{ evidence_id: 'building:B_R_0001', building_id: 'B_R_0001', label: 'Graph Visualization' }],
                districts: [{ evidence_id: 'district:C_R_0001', district_id: 'C_R_0001', name: 'Graph Research', domain_name: 'Graph, AI, and Computation' }],
                relationships: [],
                route_steps: [
                  {
                    label: 'Graph visualization',
                    target_type: 'building',
                    target_id: 'B_R_0001',
                    reason: 'Matches your question',
                  },
                ],
                filters_applied: {},
                retrieval_summary: { returned_count: 1 },
                confidence: 0.88,
                model_available: true,
              }),
            ),
          );
        }
        if (url.endsWith('/buildings')) {
          return Promise.resolve(new Response(JSON.stringify([building])));
        }
        if (url.endsWith('/bridges')) {
          return Promise.resolve(new Response(JSON.stringify([bridge])));
        }
        if (url.endsWith('/streets')) {
          return Promise.resolve(new Response(JSON.stringify([street])));
        }
        if (url.endsWith('/communities')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  community_id: 'C_R_0001',
                  color: '#6ee7f9',
                  name: 'Graph Visualization',
                  semantic_domain: 'graph_ai',
                  semantic_domain_name: 'Graph, AI, and Computation',
                },
                {
                  community_id: 'C_R_0002',
                  color: '#2edcf6',
                  name: 'Graph Retrieval',
                  semantic_domain: 'graph_ai',
                  semantic_domain_name: 'Graph, AI, and Computation',
                },
              ]),
            ),
          );
        }
        if (url.includes('/building/B_R_0001/papers')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { paper_id: 'R_000001', title: 'Paper One', publication_year: 2025, venue: 'Graph Journal', citation_count: 12, topics: ['graph visualization'] },
                { paper_id: 'R_000002', title: 'Paper Two', publication_year: 2024, venue: 'Graph Journal', citation_count: 4, topics: ['GraphRAG'] },
              ]),
            ),
          );
        }
        if (url.includes('/building/B_R_0001/edges')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  source: 'R_000001',
                  target: 'R_000002',
                  source_paper: { paper_id: 'R_000001', title: 'Paper One' },
                  target_paper: { paper_id: 'R_000002', title: 'Paper Two' },
                  edge_weight: 0.8,
                  evidence: ['shared_topic: graph visualization'],
                  components: { topic_similarity: 1 },
                },
              ]),
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify([])));
      }),
    );
  });

  it('loads city data and shows building metrics in the inspector', async () => {
    render(<App />);

    expect(screen.getByTestId('left-panel')).toHaveClass('overflow-y-auto');
    expect(await screen.findByText('Research Graph City')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('1 buildings')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /B_R_0001/i }));

    expect(screen.getByText('42 papers')).toBeInTheDocument();
    expect(screen.getAllByText('graph visualization').length).toBeGreaterThan(0);
    expect(screen.getByText('Floors')).toBeInTheDocument();
  });

  it('shows semantic color legend from communities', async () => {
    render(<App />);

    expect(await screen.findByText('Color scheme')).toBeInTheDocument();
    expect(screen.getByText('Graph Visualization')).toBeInTheDocument();
    expect(screen.getByText('Graph Retrieval')).toBeInTheDocument();
    expect(screen.getAllByText('Graph, AI, and Computation')).toHaveLength(2);
  });

  it('marks the selected building in the building list', async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText('1 buildings')).toBeInTheDocument());
    const buildingButton = screen.getByRole('button', { name: /B_R_0001/i });

    await userEvent.click(buildingButton);

    expect(buildingButton).toHaveClass('border-amber-400');
    expect(buildingButton).toHaveClass('bg-amber-50');
  });

  it('toggles bridge layer state', async () => {
    render(<App />);

    const toggle = await screen.findByRole('checkbox', { name: /Bridges/i });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
  });

  it('loads and toggles navigation streets separately from evidence bridges', async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText('1 streets')).toBeInTheDocument());
    const streets = await screen.findByRole('checkbox', { name: /Streets/i });
    const bridges = await screen.findByRole('checkbox', { name: /Bridges/i });

    expect(streets).toBeChecked();
    expect(bridges).toBeChecked();
    await userEvent.click(streets);
    expect(streets).not.toBeChecked();
    expect(bridges).toBeChecked();
  });

  it('loads papers and internal edges for a selected building', async () => {
    render(<App />);

    const buildingButtons = await screen.findAllByRole('button', { name: /B_R_0001/i });
    await userEvent.click(buildingButtons[0]);
    await userEvent.click(screen.getByRole('button', { name: 'Papers' }));

    expect(await screen.findByText('Paper One')).toBeInTheDocument();
    expect(screen.getAllByText(/Graph Journal/).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole('button', { name: 'Internal Edges' }));

    expect(await screen.findByText('Paper One -> Paper Two')).toBeInTheDocument();
    expect(screen.getByText('R_000001 -> R_000002')).toBeInTheDocument();
    expect(screen.getByText('weight 0.80')).toBeInTheDocument();
  });

  it('enters and exits a toggleable building interior graph view', async () => {
    const user = userEvent.setup();
    render(<App />);

    const buildingButtons = await screen.findAllByRole('button', { name: /B_R_0001/i });
    await user.click(buildingButtons[0]);
    await user.click(screen.getByRole('button', { name: /Enter building/i }));

    expect(await screen.findByText(/Inside B_R_0001/i)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Paper nodes/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Internal edges/i })).toBeChecked();

    await user.click(screen.getByRole('checkbox', { name: /Paper labels/i }));
    expect(screen.getByRole('checkbox', { name: /Paper labels/i })).not.toBeChecked();

    await user.click(screen.getAllByRole('button', { name: /Exit to city/i })[0]);
    expect(screen.queryByText(/Inside B_R_0001/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enter building/i })).toBeInTheDocument();
  });

  it('submits a seeded city at 100000 papers and displays queued progress', async () => {
    const user = userEvent.setup();
    render(<App />);

    const seedInput = await screen.findByLabelText('Seed papers');
    await user.type(seedInput, 'Visualizing Data using t-SNE\nFast unfolding of communities in large networks\nVisualizing Data using t-SNE');
    expect(screen.getByText('3 entries · 2 unique · 1 duplicate')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Target papers'), '100000');
    await user.click(screen.getByRole('button', { name: /Build Seeded City/i }));

    await waitFor(() => expect(screen.getByText(/Build queued/i)).toBeInTheDocument());
    expect(screen.getByText(/0 of 100,000 papers/i)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      '/api/cities',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"target_paper_count":100000'),
      }),
    );
    expect(fetch).toHaveBeenCalledWith('/api/cities/city-1/build', expect.objectContaining({ method: 'POST' }));
    expect(localStorage.getItem('researchGraphCity.activeBuild')).toContain('job-1');
  });

  it('can fill sample seed papers without manual formatting', async () => {
    const user = userEvent.setup();
    render(<App />);

    const seedInput = await screen.findByLabelText('Seed papers');
    await user.click(screen.getByRole('button', { name: /Use sample/i }));

    expect((seedInput as HTMLTextAreaElement).value).toContain('Visualizing Data using t-SNE');
    expect((seedInput as HTMLTextAreaElement).value).toContain('A Survey of Graph Neural Networks');
  });

  it('asks the research assistant and selects returned building targets', async () => {
    const user = userEvent.setup();
    render(<App />);

    const question = await screen.findByLabelText('Research question');
    await user.type(question, 'Where is graph visualization?');
    await user.click(screen.getByRole('button', { name: /Ask Research City/i }));

    expect(await screen.findByText('Start at B_R_0001 for graph visualization.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /B_R_0001/ }));

    expect(screen.getByText('42 papers')).toBeInTheDocument();
  });

  it('shows the resolved seed-only graph while a large build continues', async () => {
    localStorage.setItem('researchGraphCity.activeBuild', JSON.stringify({ cityId: 'city-1', cityType: 'seeded-city-1', jobId: 'job-1' }));

    render(<App />);

    expect(await screen.findByText('Resolved seed graph')).toBeInTheDocument();
    expect(screen.getByText('Resolved Seed Paper')).toBeInTheDocument();
    expect(screen.getByText(/Unresolved: Unresolved Paper/)).toBeInTheDocument();
  });
});
