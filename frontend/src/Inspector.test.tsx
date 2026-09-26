import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Inspector } from './Inspector';
import { useCityStore } from './store';
import type { Bridge, Building, Street } from './types';

const building: Building = {
  building_id: 'B_R_0001',
  city_type: 'research',
  vertex_ids: ['R_000001', 'R_000002'],
  node_count: 2,
  edge_count: 1,
  internal_density: 0.5,
  avg_core: 2,
  max_core: 3,
  height: 20,
  footprint: 8,
  x: 0,
  z: 0,
  top_labels: ['graph visualization', 'GraphRAG'],
  profile: { topics: ['graph visualization'] },
  original_labels: {
    topics: ['graph visualization', 'GraphRAG', 'network analysis'],
    keywords: ['city layout', 'citation graph'],
  },
  activation: { score: 0.6 },
  activation_score: 0.6,
  floors: [{ floor_id: 'F_R_0001_01', floor_index: 1, node_count: 1, vertex_ids: ['R_000001'], top_labels: ['graph visualization'] }],
  summary: null,
  community_id: 'C_R_0001',
};

const bridge: Bridge = {
  bridge_id: 'BR_R_0001_0002',
  city_type: 'research',
  source_building_id: 'B_R_0001',
  target_building_id: 'B_R_0002',
  bridge_strength: 0.7,
  bridge_type: 'semantic_structural',
  components: { cross_edge_strength: 0.45, semantic_similarity: 0.6 },
  evidence: ['cross_edges: 12', 'shared_label: graph visualization'],
  summary: null,
  activation_score: 0.5,
};

const street: Street = {
  street_id: 'ST_R_0002_0003',
  city_type: 'research',
  source_building_id: 'B_R_0002',
  target_building_id: 'B_R_0003',
  street_type: 'research_backbone',
  distance: 120,
  street_score: 0.42,
  components: {
    normalized_cross_edge_count: 0.25,
    profile_similarity: 0.5,
    shared_label_similarity: 0.33,
    semantic_similarity: 0.4,
  },
  evidence: ['cross_edges: 4', 'shared_label: topic modeling', 'research_backbone'],
};

describe('Inspector', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/building/B_R_0001/papers')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  paper_id: 'R_000001',
                  title: 'Graph City Paper',
                  publication_year: 2025,
                  venue: 'Graph Journal',
                  topics: ['graph visualization'],
                  keywords: ['city layout'],
                },
              ]),
            ),
          );
        }
        if (url.includes('/bridge/BR_R_0001_0002/edges')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  source: 'R_000001',
                  target: 'R_000101',
                  source_paper: { paper_id: 'R_000001', title: 'Source Graph Paper' },
                  target_paper: { paper_id: 'R_000101', title: 'Target Mobility Paper' },
                  edge_weight: 0.74,
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

  it('inspects original labels before raw vertex ids', async () => {
    render(<Inspector building={building} bridge={null} />);

    expect(screen.getByText('Original Label Inspection')).toBeInTheDocument();
    expect(screen.getByText('topics')).toBeInTheDocument();
    expect(screen.getByText('city layout')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Inspect paper labels' }));

    expect(await screen.findByText('Graph City Paper')).toBeInTheDocument();
    expect(screen.getByText('city layout')).toBeInTheDocument();
    expect(screen.getByText('R_000001')).toBeInTheDocument();
  });

  it('pages every original wave and filters papers by a wave outside the scene preview', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/floors')) {
        const cursor = Number(new URL(url, 'http://localhost').searchParams.get('cursor'));
        return Promise.resolve(new Response(JSON.stringify(Array.from({length: cursor ? 51 : 100}, (_, i) => ({
          floor_id: `F${cursor+i+1}`, floor_index: cursor+i+1, node_count: 1,
        })))));
      }
      return Promise.resolve(new Response(JSON.stringify([])));
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<Inspector building={{...building, floor_count: 151, floors_truncated: true,
      quality_metrics: {algorithm: 'graph-cities-v1'}, floors: []}} bridge={null} />);
    await screen.findByText('Floor 100');
    await userEvent.click(screen.getByRole('button', {name: 'Next floor page'}));
    await userEvent.click(await screen.findByText('Floor 101'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('floor_id=F101')));
  });

  it('browses beyond 200 papers in one wave and opens a later paper', async () => {
    const rows = Array.from({length: 201}, (_, i) => ({
      paper_id: `P${String(i).padStart(4, '0')}`, title: `Study number ${i}`,
    }));
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const params = new URL(url, 'http://localhost').searchParams;
      const cursor = params.get('cursor');
      const items = rows.filter(p => !cursor || p.paper_id > cursor).slice(0, Number(params.get('limit') ?? 200));
      return Promise.resolve(new Response(JSON.stringify(items)));
    }));
    useCityStore.setState({interiorPapers: rows.slice(0, 200), interiorActive: true, selectedPaperId: null});
    render(<Inspector building={building} bridge={null} onSelectPaper={useCityStore.getState().selectPaper} />);
    await userEvent.click(screen.getByRole('button', {name: 'Inspect paper labels'}));
    await screen.findByText('Study number 0');
    for (let page = 1; page <= 4; page++) {
      await userEvent.click(screen.getByRole('button', {name: 'Next paper page'}));
      await screen.findByText(`Study number ${page * 50}`);
    }
    expect(screen.getByRole('button', {name: 'Next paper page'})).toBeDisabled();
    await userEvent.click(screen.getByText('Study number 200'));
    const state = useCityStore.getState();
    expect(state.selectedPaperId).toBe('P0200');
    expect(state.interiorPapers.find(p => p.paper_id === state.selectedPaperId)?.title).toBe('Study number 200');
    expect(state.interiorPapers.length).toBeLessThanOrEqual(200);
    await userEvent.click(screen.getByRole('button', {name: 'Previous paper page'}));
    expect(await screen.findByText('Study number 150')).toBeInTheDocument();
  });

  it('pages internal edges beyond the initial preview', async () => {
    const edges = Array.from({length: 161}, (_, i) => ({source: `P${String(i).padStart(4, '0')}`, target: 'Q', edge_type: 'citation', edge_weight: 1}));
    edges.splice(80, 0, {...edges[79], edge_type: 'similarity'});
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const params = new URL(url, 'http://localhost').searchParams;
      const cursor = params.get('cursor');
      return Promise.resolve(new Response(JSON.stringify(edges.filter(e => !cursor || (cursor.split(':').length === 3 ? `${e.source}:${e.target}:${e.edge_type}` : `${e.source}:${e.target}`) > cursor).slice(0, Number(params.get('limit') ?? 200)))));
    }));
    render(<Inspector building={building} bridge={null} />);
    await userEvent.click(screen.getByRole('button', {name: 'Internal Edges'}));
    await screen.findAllByText('P0000 -> Q');
    await userEvent.click(screen.getByRole('button', {name: 'Next edge page'}));
    expect((await screen.findAllByText('P0080 -> Q')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('P0079 -> Q').length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', {name: 'Next edge page'}));
    expect((await screen.findAllByText('P0160 -> Q')).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', {name: 'Next edge page'})).toBeDisabled();
  });

  it('shows original wave and fragment provenance for the selected floor', async () => {
    render(<Inspector building={{...building, floors: [{...building.floors[0], summary: {
      algorithm: 'graph-cities-v1', wave: 0, fragments: {'0': 3, '1': 2}, internal_edges: 4, external_edges: 1,
    }}]}} bridge={null} />);
    await userEvent.click(screen.getByRole('button', {name: 'Papers'}));
    await userEvent.click(screen.getByRole('button', {name: 'Floor 1'}));
    expect(screen.getByText('Original wave 0')).toBeInTheDocument();
    expect(screen.getByText('Fragment 0: 3 vertices')).toBeInTheDocument();
    expect(screen.getByText('Fragment 1: 2 vertices')).toBeInTheDocument();
  });

  it('shows bridge cross edges and explains summary evidence', async () => {
    render(<Inspector building={null} bridge={bridge} street={null} />);

    expect(screen.getByText('Cross Edges')).toBeInTheDocument();
    expect(screen.getByText(/paper-level links between the two buildings/i)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('Source Graph Paper -> Target Mobility Paper')).toBeInTheDocument());
    expect(screen.getByText('R_000001 -> R_000101')).toBeInTheDocument();
    expect(screen.getByText('weight 0.74')).toBeInTheDocument();
    expect(screen.getByText(/cross_edge_strength/i)).toBeInTheDocument();
  });

  it('shows research street relationship evidence and score components', () => {
    render(<Inspector building={null} bridge={null} street={street} />);

    expect(screen.getByText('Street inspector')).toBeInTheDocument();
    expect(screen.getAllByText('research_backbone').length).toBeGreaterThan(0);
    expect(screen.getByText('0.42')).toBeInTheDocument();
    expect(screen.getByText('cross_edges: 4')).toBeInTheDocument();
    expect(screen.getByText('normalized cross edge count')).toBeInTheDocument();
    expect(screen.getByText(/weaker research relationship/i)).toBeInTheDocument();
    expect(screen.queryByText('layout proximity')).not.toBeInTheDocument();
  });

  it('identifies original streets as geometry without a research score', () => {
    render(<Inspector building={null} bridge={null} street={{...street, street_type: 'graph_city_geometry', evidence: [], components: {visual_only: true, algorithm: 'graph-cities-v1'} as unknown as Record<string, number>}} />);
    expect(screen.getByText(/geometric adjacency/i)).toBeInTheDocument();
    expect(screen.queryByText('Street Formula')).not.toBeInTheDocument();
  });

  it('navigates to another building containing the selected paper', async () => {
    const selectBuilding = vi.fn();
    render(<Inspector building={building} bridge={null} onSelectBuilding={selectBuilding}
      selectedPaper={{paper_id: 'P1', title: 'Shared', locations: [
        {building_id: 'B_OTHER', building_label: 'Other fixed point', floors: []},
      ]}} />);
    await userEvent.click(screen.getByRole('button', {name: 'Other fixed point'}));
    expect(selectBuilding).toHaveBeenCalledWith('B_OTHER');
  });
});
