import { BookOpen, DoorOpen, FileText, LogOut, Network, Route, Tags } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { fetchBridgeCrossEdges, fetchBuildingEdges, fetchBuildingPapers } from './api';
import type {
  Bridge,
  Building,
  CityType,
  ResearchEdgeDetail,
  ResearchPaper,
  Street,
} from './types';

interface InspectorProps {
  cityType?: CityType;
  building: Building | null;
  bridge: Bridge | null;
  street?: Street | null;
  selectedPaper?: ResearchPaper | null;
  interiorEdges?: ResearchEdgeDetail[];
  interiorActive?: boolean;
  interiorLoading?: boolean;
  interiorError?: string | null;
  onEnterInterior?: () => void;
  onExitInterior?: () => void;
  onSelectPaper?: (id: string | null) => void;
}

export function Inspector({
  cityType = 'research',
  building,
  bridge,
  street,
  selectedPaper = null,
  interiorEdges = [],
  interiorActive = false,
  interiorLoading = false,
  interiorError = null,
  onEnterInterior,
  onExitInterior,
  onSelectPaper,
}: InspectorProps) {
  if (bridge) {
    return <BridgeInspector cityType={cityType} bridge={bridge} />;
  }

  if (street) {
    return <StreetInspector street={street} />;
  }

  if (!building) {
    return (
      <aside className="h-full w-96 overflow-auto border-l border-slate-200 bg-white p-5 text-slate-900 shadow-xl max-md:h-auto max-md:w-full max-md:border-l-0 max-md:border-t">
        <Header icon={<Network size={18} />} title="Inspector" subtitle="Select a building, bridge, or street" />
        <p className="mt-4 text-sm text-slate-600">Hover for quick labels. Click a building to inspect papers, density, floors, and semantic labels.</p>
      </aside>
    );
  }

  return (
    <BuildingInspector
      cityType={cityType}
      building={building}
      selectedPaper={selectedPaper}
      interiorEdges={interiorEdges}
      interiorActive={interiorActive}
      interiorLoading={interiorLoading}
      interiorError={interiorError}
      onEnterInterior={onEnterInterior}
      onExitInterior={onExitInterior}
      onSelectPaper={onSelectPaper}
    />
  );
}

function StreetInspector({ street }: { street: Street }) {
  return (
    <aside className="h-full w-96 overflow-auto border-l border-slate-200 bg-white p-5 text-slate-900 shadow-xl max-md:h-auto max-md:w-full max-md:border-l-0 max-md:border-t">
      <Header icon={<Route size={18} />} title={street.street_id} subtitle="Street inspector" />
      <MetricGrid
        items={[
          ['Score', street.street_score.toFixed(2)],
          ['Type', street.street_type],
          ['Distance', street.distance.toFixed(1)],
        ]}
      />
      <Section title="Building Relationship">
        <div className="rounded border border-slate-200 p-3 text-sm">
          <div className="font-medium">
            {street.source_building_id} {'->'} {street.target_building_id}
          </div>
          <p className="mt-2 text-slate-600">
            This is a weaker research relationship than a bridge. It comes only from paper cross edges, shared labels, profile overlap, and semantic
            similarity.
          </p>
        </div>
      </Section>
      <Section title="Evidence">
        {street.evidence.length ? street.evidence.map((item) => <Pill key={item}>{item}</Pill>) : <p className="text-sm text-slate-500">No street evidence.</p>}
      </Section>
      <Section title="Component Scores">
        {Object.entries(street.components).map(([key, value]) => (
          <div key={key} className="flex justify-between border-b border-slate-100 py-1 text-sm">
            <span>{key.replaceAll('_', ' ')}</span>
            <span className="font-mono">{value.toFixed(2)}</span>
          </div>
        ))}
      </Section>
      <Section title="Street Formula">
        <div className="rounded border border-slate-200 p-3 text-sm leading-5 text-slate-600">
          street_score = 0.45 cross-edge count + 0.25 profile similarity + 0.20 shared labels + 0.10 semantic similarity.
        </div>
      </Section>
    </aside>
  );
}

function BridgeInspector({ cityType, bridge }: { cityType: CityType; bridge: Bridge }) {
  const [crossEdges, setCrossEdges] = useState<ResearchEdgeDetail[]>([]);
  const [status, setStatus] = useState<'loading' | 'idle' | 'error'>('loading');
  const evidenceCrossEdgeCount = bridge.evidence.find((item) => item.startsWith('cross_edges:'))?.replace('cross_edges:', '').trim() ?? '0';
  const sharedLabels = bridge.evidence
    .filter((item) => item.startsWith('shared_label:'))
    .map((item) => item.replace('shared_label:', '').trim());

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    fetchBridgeCrossEdges(cityType, bridge.bridge_id)
      .then((items) => {
        if (!cancelled) {
          setCrossEdges(items);
          setStatus('idle');
        }
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [bridge.bridge_id, cityType]);

  return (
    <aside className="h-full w-96 overflow-auto border-l border-slate-200 bg-white p-5 text-slate-900 shadow-xl max-md:h-auto max-md:w-full max-md:border-l-0 max-md:border-t">
      <Header icon={<Route size={18} />} title={bridge.bridge_id} subtitle="Bridge inspector" />
      <MetricGrid items={[['Strength', bridge.bridge_strength.toFixed(2)], ['Activation', bridge.activation_score.toFixed(2)], ['Type', bridge.bridge_type]]} />
      <Section title="Building Relationship">
        <div className="rounded border border-slate-200 p-3 text-sm">
          <div className="font-medium">
            {bridge.source_building_id} {'->'} {bridge.target_building_id}
          </div>
          <div className="mt-1 text-slate-600">Cross edges: {evidenceCrossEdgeCount}</div>
          <div className="mt-2">
            {sharedLabels.length ? sharedLabels.map((label) => <Pill key={label}>{label}</Pill>) : <p className="text-sm text-slate-500">No shared labels.</p>}
          </div>
        </div>
      </Section>
      <Section title="Cross Edges">
        <HeaderLine icon={<Network size={15} />} text="Paper-level links between the two buildings" />
        <p className="mb-3 text-sm leading-5 text-slate-600">
          These cross edges are the structural evidence for this bridge. The count is normalized into cross_edge_strength, combined into bridge_strength,
          and included with shared labels as compact evidence for generated bridge summaries.
        </p>
        {status === 'loading' && <p className="text-sm text-slate-500">Loading cross edges...</p>}
        {status === 'error' && <p className="text-sm text-red-600">Could not load cross edges.</p>}
        {status !== 'loading' && crossEdges.length === 0 && <p className="text-sm text-slate-500">No cross edges found for this bridge.</p>}
        <div className="space-y-2">
          {crossEdges.slice(0, 80).map((edge) => (
            <div key={`${edge.source}-${edge.target}-${edge.edge_weight}`} className="rounded border border-slate-200 p-3 text-sm">
              <EdgeHeader edge={edge} />
              <div className="mt-1 text-slate-600">weight {edge.edge_weight.toFixed(2)}</div>
              <div className="mt-2">
                {(edge.evidence ?? []).slice(0, 4).map((item) => (
                  <Pill key={`${edge.source}-${edge.target}-${item}`}>{item}</Pill>
                ))}
              </div>
              {edge.components && (
                <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-slate-600">
                  {Object.entries(edge.components)
                    .slice(0, 6)
                    .map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-2">
                        <span>{key.replaceAll('_', ' ')}</span>
                        <span className="font-mono">{value.toFixed(2)}</span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
        {crossEdges.length > 80 && <p className="mt-2 text-xs text-slate-500">Showing 80 of {crossEdges.length} cross edges.</p>}
      </Section>
      <Section title="Evidence">
        {bridge.evidence.length ? bridge.evidence.map((item) => <Pill key={item}>{item}</Pill>) : <p className="text-sm text-slate-500">No evidence labels.</p>}
      </Section>
      <Section title="Component Scores">
        {Object.entries(bridge.components).map(([key, value]) => (
          <div key={key} className="flex justify-between border-b border-slate-100 py-1 text-sm">
            <span>{key.replaceAll('_', ' ')}</span>
            <span className="font-mono">{value.toFixed(2)}</span>
          </div>
        ))}
      </Section>
      <Section title="Metric Definitions">
        <DefinitionList />
      </Section>
    </aside>
  );
}

function BuildingInspector({
  cityType,
  building,
  selectedPaper,
  interiorEdges,
  interiorActive,
  interiorLoading,
  interiorError,
  onEnterInterior,
  onExitInterior,
  onSelectPaper,
}: {
  cityType: CityType;
  building: Building;
  selectedPaper: ResearchPaper | null;
  interiorEdges: ResearchEdgeDetail[];
  interiorActive: boolean;
  interiorLoading: boolean;
  interiorError: string | null;
  onEnterInterior?: () => void;
  onExitInterior?: () => void;
  onSelectPaper?: (id: string | null) => void;
}) {
  const [selectedTerm, setSelectedTerm] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'papers' | 'edges'>('overview');
  const [selectedFloorId, setSelectedFloorId] = useState<string | null>(null);
  const [papers, setPapers] = useState<ResearchPaper[]>([]);
  const [edges, setEdges] = useState<ResearchEdgeDetail[]>([]);
  const [detailStatus, setDetailStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const summary = useMemo(() => buildingSummaryText(building), [building]);
  const summaryWords = useMemo(() => summary.split(/(\s+)/), [summary]);
  const originalLabels = building.original_labels ?? {};
  const connectedEdges = useMemo(() => {
    if (!selectedPaper) return [];
    return interiorEdges
      .filter((edge) => edge.source === selectedPaper.paper_id || edge.target === selectedPaper.paper_id)
      .sort((a, b) => b.edge_weight - a.edge_weight);
  }, [interiorEdges, selectedPaper]);

  useEffect(() => {
    setActiveTab('overview');
    setSelectedFloorId(null);
    setSelectedTerm(null);
    setPapers([]);
    setEdges([]);
    setDetailStatus('idle');
  }, [building.building_id]);

  useEffect(() => {
    if (interiorActive && selectedPaper) {
      setActiveTab('edges');
    }
  }, [interiorActive, selectedPaper?.paper_id]);

  useEffect(() => {
    if (activeTab === 'overview') return;
    if (interiorActive && selectedPaper && activeTab === 'edges') return;
    let cancelled = false;
    setDetailStatus('loading');
    const request =
      activeTab === 'papers'
        ? fetchBuildingPapers(cityType, building.building_id, selectedFloorId).then((items) => {
            if (!cancelled) setPapers(items);
          })
        : fetchBuildingEdges(cityType, building.building_id, selectedFloorId).then((items) => {
            if (!cancelled) setEdges(items);
          });
    request
      .then(() => {
        if (!cancelled) setDetailStatus('idle');
      })
      .catch(() => {
        if (!cancelled) setDetailStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, building.building_id, cityType, selectedFloorId, interiorActive, selectedPaper?.paper_id]);

  return (
    <aside className="h-full w-96 overflow-auto border-l border-slate-200 bg-white p-5 text-slate-900 shadow-xl max-md:h-auto max-md:w-full max-md:border-l-0 max-md:border-t">
      <Header
        icon={<BookOpen size={18} />}
        title={building.building_id}
        subtitle={interiorActive ? 'Interior graph view' : building.top_labels[0] ?? 'Research building'}
      />
      <div className="mt-4 space-y-2">
        {interiorActive ? (
          <button
            type="button"
            className="inline-flex w-full items-center justify-center gap-2 rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50"
            onClick={() => onExitInterior?.()}
          >
            <LogOut size={15} />
            Exit to city
          </button>
        ) : (
          <button
            type="button"
            className="inline-flex w-full items-center justify-center gap-2 rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
            onClick={() => onEnterInterior?.()}
          >
            <DoorOpen size={15} />
            Enter building
          </button>
        )}
        {interiorLoading && <p className="text-xs text-slate-500">Loading internal papers and edges...</p>}
        {interiorError && <p className="text-xs text-red-600">{interiorError}</p>}
      </div>
      {selectedPaper && (
        <Section title="Selected paper">
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm">
            <div className="font-medium">{selectedPaper.title}</div>
            <div className="mt-1 font-mono text-xs text-slate-500">{selectedPaper.paper_id}</div>
            <div className="mt-1 text-slate-600">
              {[selectedPaper.publication_year, selectedPaper.venue, selectedPaper.citation_count !== undefined ? `${selectedPaper.citation_count} citations` : null]
                .filter(Boolean)
                .join(' | ')}
            </div>
            <div className="mt-2 text-xs text-slate-500">{connectedEdges.length} connected edges in this building</div>
            <button
              type="button"
              className="mt-2 text-xs font-medium text-slate-600 underline"
              onClick={() => onSelectPaper?.(null)}
            >
              Unselect paper
            </button>
          </div>
        </Section>
      )}
      <MetricGrid
        items={[
          ['Papers', `${building.node_count} papers`],
          ['Edges', building.edge_count.toString()],
          ['Density', building.internal_density.toFixed(2)],
          ['Avg core', building.avg_core.toFixed(2)],
          ['Activation', building.activation_score.toFixed(2)],
          ['Community', building.community_id ?? 'unassigned'],
        ]}
      />
      <div className="mt-5 grid grid-cols-3 gap-1 rounded bg-slate-100 p-1 text-sm">
        {[
          ['overview', 'Overview'],
          ['papers', 'Papers'],
          ['edges', 'Internal Edges'],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`rounded px-2 py-1 ${activeTab === key ? 'bg-white font-semibold shadow-sm' : 'text-slate-600 hover:bg-white/70'}`}
            onClick={() => setActiveTab(key as 'overview' | 'papers' | 'edges')}
          >
            {label}
          </button>
        ))}
      </div>
      {activeTab !== 'overview' && (
        <div className="mt-3">
          <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Floor filter</div>
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              className={`rounded px-2 py-1 text-xs ${selectedFloorId === null ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700'}`}
              onClick={() => setSelectedFloorId(null)}
            >
              All floors
            </button>
            {building.floors.map((floor) => (
              <button
                key={floor.floor_id}
                type="button"
                className={`rounded px-2 py-1 text-xs ${selectedFloorId === floor.floor_id ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700'}`}
                onClick={() => setSelectedFloorId(floor.floor_id)}
              >
                Floor {floor.floor_index ?? '?'}
              </button>
            ))}
          </div>
        </div>
      )}
      {activeTab === 'overview' && (
        <>
          <Section title="Generated Summary">
            <div className="rounded border border-slate-200 p-3 text-sm leading-6">
              {summaryWords.map((word, index) => {
                const normalized = cleanTerm(word);
                const selectable = normalized.length > 2 && labelMatchesTerm(originalLabels, normalized);
                return (
                  <button
                    key={`${word}-${index}`}
                    type="button"
                    className={selectable ? 'rounded px-1 font-medium text-sky-700 hover:bg-sky-50' : 'cursor-text px-0.5 text-slate-700'}
                    onClick={() => selectable && setSelectedTerm(normalized)}
                  >
                    {word}
                  </button>
                );
              })}
            </div>
          </Section>
          <Section title="Top Labels">
            {building.top_labels.map((label) => (
              <Pill key={label} active={selectedTerm ? label.toLowerCase().includes(selectedTerm) : false}>
                {label}
              </Pill>
            ))}
          </Section>
          <Section title="Original Label Inspection">
            <HeaderLine icon={<Tags size={15} />} text={selectedTerm ? `Highlighting "${selectedTerm}"` : 'Showing subset by label type'} />
            {Object.entries(originalLabels).map(([group, labels]) => (
              <div key={group} className="mb-3">
                <div className="mb-1 text-xs font-semibold uppercase text-slate-500">{group}</div>
                {labels.slice(0, 8).map((label) => (
                  <Pill key={`${group}-${label}`} active={selectedTerm ? label.toLowerCase().includes(selectedTerm) : false}>
                    {label}
                  </Pill>
                ))}
                {labels.length > 8 && <span className="text-xs text-slate-500">+{labels.length - 8} more</span>}
              </div>
            ))}
            <button
              type="button"
              className="mt-1 inline-flex items-center gap-2 rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
              onClick={() => setActiveTab('papers')}
            >
              <FileText size={15} />
              Inspect paper labels
            </button>
          </Section>
          <Section title="Floors">
            <div className="space-y-2">
              {building.floors.map((floor) => (
                <button
                  key={floor.floor_id}
                  type="button"
                  className="w-full rounded border border-slate-200 p-2 text-left text-sm hover:bg-slate-50"
                  onClick={() => {
                    setSelectedFloorId(floor.floor_id);
                    setActiveTab('papers');
                  }}
                >
                  <div className="font-medium">Floor {floor.floor_index ?? '?'}</div>
                  <div className="text-slate-600">
                    {floor.node_count ?? 0} papers, core {floor.core_range?.[0] ?? '?'}-{floor.core_range?.[1] ?? '?'}
                  </div>
                </button>
              ))}
            </div>
          </Section>
        </>
      )}
      {activeTab === 'papers' && (
        <Section title="Papers">
          {detailStatus === 'loading' && <p className="text-sm text-slate-500">Loading papers...</p>}
          {detailStatus === 'error' && <p className="text-sm text-red-600">Could not load papers.</p>}
          {detailStatus !== 'loading' && papers.length === 0 && <p className="text-sm text-slate-500">No papers for this filter.</p>}
          <div className="space-y-2">
            {papers.slice(0, 50).map((paper) => {
              const selected = selectedPaper?.paper_id === paper.paper_id;
              return (
                <button
                  key={paper.paper_id}
                  type="button"
                  className={`w-full rounded border p-3 text-left text-sm ${
                    selected ? 'border-amber-400 bg-amber-50' : 'border-slate-200 hover:bg-slate-50'
                  }`}
                  onClick={() => onSelectPaper?.(paper.paper_id)}
                >
                  <div className="font-medium">{paper.title}</div>
                  <div className="mt-1 font-mono text-xs text-slate-500">{paper.paper_id}</div>
                  <div className="mt-1 text-slate-600">
                    {[paper.publication_year, paper.venue, paper.citation_count !== undefined ? `${paper.citation_count} citations` : null].filter(Boolean).join(' | ')}
                  </div>
                  <div className="mt-2">
                    <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Original labels</div>
                    {[...(paper.topics ?? []), ...(paper.keywords ?? [])].slice(0, 8).map((label) => (
                      <Pill key={`${paper.paper_id}-${label}`}>{label}</Pill>
                    ))}
                  </div>
                </button>
              );
            })}
          </div>
          {papers.length > 50 && <p className="mt-2 text-xs text-slate-500">Showing 50 of {papers.length} papers.</p>}
        </Section>
      )}
      {activeTab === 'edges' && (
        <Section title={selectedPaper ? 'Connected Edges' : 'Internal Edges'}>
          {selectedPaper ? (
            <>
              <HeaderLine icon={<Network size={15} />} text={`Edges linked to ${selectedPaper.title}`} />
              {connectedEdges.length === 0 && <p className="text-sm text-slate-500">No connected edges for this paper in the loaded interior graph.</p>}
              <div className="space-y-2">
                {connectedEdges.slice(0, 80).map((edge) => (
                  <div key={`${edge.source}-${edge.target}-${edge.edge_weight}`} className="rounded border border-slate-200 p-3 text-sm">
                    <EdgeHeader edge={edge} />
                    <div className="mt-1 text-slate-600">weight {edge.edge_weight.toFixed(2)}</div>
                    <div className="mt-2">
                      {(edge.evidence ?? []).slice(0, 4).map((item) => (
                        <Pill key={`${edge.source}-${edge.target}-${item}`}>{item}</Pill>
                      ))}
                    </div>
                    {edge.components && (
                      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-slate-600">
                        {Object.entries(edge.components)
                          .slice(0, 6)
                          .map(([key, value]) => (
                            <div key={key} className="flex justify-between gap-2">
                              <span>{key.replaceAll('_', ' ')}</span>
                              <span className="font-mono">{value.toFixed(2)}</span>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {connectedEdges.length > 80 && <p className="mt-2 text-xs text-slate-500">Showing 80 of {connectedEdges.length} edges.</p>}
            </>
          ) : (
            <>
              {detailStatus === 'loading' && <p className="text-sm text-slate-500">Loading edges...</p>}
              {detailStatus === 'error' && <p className="text-sm text-red-600">Could not load edges.</p>}
              {detailStatus !== 'loading' && edges.length === 0 && <p className="text-sm text-slate-500">No internal edges for this filter.</p>}
              <div className="space-y-2">
                {edges.slice(0, 80).map((edge) => (
                  <div key={`${edge.source}-${edge.target}-${edge.edge_weight}`} className="rounded border border-slate-200 p-3 text-sm">
                    <EdgeHeader edge={edge} />
                    <div className="mt-1 text-slate-600">weight {edge.edge_weight.toFixed(2)}</div>
                    <div className="mt-2">
                      {(edge.evidence ?? []).slice(0, 4).map((item) => (
                        <Pill key={`${edge.source}-${edge.target}-${item}`}>{item}</Pill>
                      ))}
                    </div>
                    {edge.components && (
                      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-slate-600">
                        {Object.entries(edge.components)
                          .slice(0, 6)
                          .map(([key, value]) => (
                            <div key={key} className="flex justify-between gap-2">
                              <span>{key.replaceAll('_', ' ')}</span>
                              <span className="font-mono">{value.toFixed(2)}</span>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {edges.length > 80 && <p className="mt-2 text-xs text-slate-500">Showing 80 of {edges.length} edges.</p>}
            </>
          )}
        </Section>
      )}
    </aside>
  );
}

function buildingSummaryText(building: Building) {
  const labels = building.top_labels.slice(0, 3).join(', ');
  return `${building.building_id} groups ${building.node_count} papers around ${labels}. Its ${building.floors.length} floors show paper bands within the building, and community ${building.community_id ?? 'unassigned'} links it to related buildings.`;
}

function EdgeHeader({ edge }: { edge: ResearchEdgeDetail }) {
  const sourceTitle = edge.source_paper?.title?.trim() || edge.source;
  const targetTitle = edge.target_paper?.title?.trim() || edge.target;
  const sourceMeta = paperMeta(edge.source_paper);
  const targetMeta = paperMeta(edge.target_paper);
  return (
    <div>
      <div className="text-sm font-semibold leading-5 text-slate-900">
        {sourceTitle} {'->'} {targetTitle}
      </div>
      <div className="mt-1 font-mono text-xs text-slate-500">
        {edge.source} {'->'} {edge.target}
      </div>
      {(sourceMeta || targetMeta) && (
        <div className="mt-1 text-xs text-slate-500">
          {[sourceMeta, targetMeta].filter(Boolean).join(' -> ')}
        </div>
      )}
    </div>
  );
}

function paperMeta(paper: ResearchEdgeDetail['source_paper']) {
  if (!paper) return '';
  return [paper.publication_year, paper.venue].filter(Boolean).join(' | ');
}

function cleanTerm(word: string) {
  return word.toLowerCase().replace(/[^a-z0-9-]/g, '');
}

function labelMatchesTerm(groups: Record<string, string[]>, term: string) {
  return Object.values(groups).some((labels) => labels.some((label) => label.toLowerCase().includes(term)));
}

function Header({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded bg-slate-900 text-white">{icon}</div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-slate-500">{subtitle}</p>
      </div>
    </div>
  );
}

function MetricGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="mt-5 grid grid-cols-2 gap-2">
      {items.map(([label, value]) => (
        <div key={label} className="rounded border border-slate-200 p-3">
          <div className="text-xs uppercase text-slate-500">{label}</div>
          <div className="mt-1 text-sm font-semibold">{value}</div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </section>
  );
}

function Pill({ children, active = false }: { children: React.ReactNode; active?: boolean }) {
  return <span className={`mb-2 mr-2 inline-flex rounded px-2 py-1 text-sm ${active ? 'bg-amber-200 text-amber-950' : 'bg-slate-100 text-slate-700'}`}>{children}</span>;
}

function HeaderLine({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
      {icon}
      {text}
    </div>
  );
}

function DefinitionList() {
  const definitions = [
    ['Profile similarity', '0.30 J(topics) + 0.20 J(methods) + 0.15 J(datasets) + 0.10 J(venues) + 0.10 J(institutions).'],
    ['Semantic similarity', '0.5 J(top labels) + 0.5 J(profile topics + keywords).'],
    ['Cross-edge strength', 'min(1, cross_building_edge_count / sqrt(source_node_count * target_node_count)).'],
    ['Vertex overlap', 'Shared paper vertices divided by union paper vertices; currently 0 because buildings are disjoint.'],
    ['Activation similarity', '1 - abs(source_activation - target_activation).'],
    ['LLM confidence', 'A reserved confidence prior for summary evidence, currently fixed at 0.5 until per-bridge LLM scoring is added.'],
    ['Bridge strength', '0.25 profile + 0.25 semantic + 0.25 cross-edge + 0.10 vertex overlap + 0.10 activation + 0.05 LLM confidence.'],
  ];
  return (
    <div className="space-y-2">
      {definitions.map(([term, definition]) => (
        <div key={term} className="rounded border border-slate-200 p-2 text-sm">
          <div className="font-medium">{term}</div>
          <div className="mt-1 text-slate-600">{definition}</div>
        </div>
      ))}
    </div>
  );
}
