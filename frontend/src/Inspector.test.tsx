import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Inspector } from './Inspector';
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
});
