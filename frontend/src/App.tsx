import { Activity, Building2, Compass, Download, GitBranch, Layers, Route, Sparkles, Tag } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { compareCities, exportEvidenceReport, fetchCities, fetchTimeline } from './api';
import { CityScene } from './CityScene';
import { Inspector } from './Inspector';
import { useCityStore } from './store';
import type { LayerState } from './types';
import type { CityComparisonResponse, CitySummary, TimelineResponse } from './types';

const layerLabels: Array<[keyof LayerState, string, React.ReactNode]> = [
  ['buildings', 'Buildings', <Building2 size={16} key="buildings" />],
  ['bridges', 'Bridges', <GitBranch size={16} key="bridges" />],
  ['streets', 'Streets', <Route size={16} key="streets" />],
  ['communities', 'Semantic Communities', <Layers size={16} key="communities" />],
  ['activation', 'Activation Glow', <Activity size={16} key="activation" />],
  ['floors', 'Floor Segments', <Layers size={16} key="floors" />],
  ['labels', 'Labels', <Tag size={16} key="labels" />],
];

const sampleSeedPapers = [
  'Visualizing Data using t-SNE',
  'Fast unfolding of communities in large networks',
  'Graph Attention Networks',
  'Semi-Supervised Classification with Graph Convolutional Networks',
  'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks',
  'Attention Is All You Need',
  'The PageRank Citation Ranking: Bringing Order to the Web',
  'DeepWalk: Online Learning of Social Representations',
  'node2vec: Scalable Feature Learning for Networks',
  'A Survey of Graph Neural Networks',
].join('\n');

export default function App() {
  const [seedText, setSeedText] = useState('');
  const [targetPaperCount, setTargetPaperCount] = useState(1000);
  const [navigationQuestion, setNavigationQuestion] = useState('');
  const [assistantYearMin, setAssistantYearMin] = useState('');
  const [assistantYearMax, setAssistantYearMax] = useState('');
  const [assistantOpenAccess, setAssistantOpenAccess] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [availableCities, setAvailableCities] = useState<CitySummary[]>([]);
  const [compareCityId, setCompareCityId] = useState('');
  const [comparison, setComparison] = useState<CityComparisonResponse | null>(null);
  const {
    cityMode,
    buildings,
    bridges,
    streets,
    communities,
    layers,
    loading,
    error,
    selectedBuildingId,
    selectedBridgeId,
    selectedStreetId,
    selectedPaperId,
    interiorActive,
    interiorLoading,
    interiorError,
    interiorPapers,
    interiorEdges,
    interiorLayers,
    seedBuildStatus,
    seedBuildMessage,
    seedBuildJob,
    seedGraph,
    navigationStatus,
    navigationError,
    navigationResponse,
    loadCity,
    buildSeededCity,
    cancelSeedBuild,
    resumeSeedBuild,
    askCityNavigator,
    selectBuilding,
    selectBridge,
    selectStreet,
    selectPaper,
    enterBuildingInterior,
    exitBuildingInterior,
    toggleLayer,
    toggleInteriorLayer,
  } = useCityStore();

  useEffect(() => {
    void loadCity('research');
    void resumeSeedBuild();
  }, [loadCity, resumeSeedBuild]);

  useEffect(() => {
    void fetchTimeline(cityMode)
      .then((value) => setTimeline(value && Array.isArray(value.years) ? value : null))
      .catch(() => setTimeline(null));
    void fetchCities().then((cities) => setAvailableCities(Array.isArray(cities) ? cities : [])).catch(() => setAvailableCities([]));
    setComparison(null);
  }, [cityMode, buildings.length]);

  const seedStats = useMemo(() => {
    const entries = seedText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    const unique = new Set(entries.map((item) => item.toLocaleLowerCase())).size;
    return { entries: entries.length, unique, duplicates: entries.length - unique };
  }, [seedText]);
  const seedInputValid = seedStats.unique > 0 && seedStats.unique <= 30;
  const assistantFilters = useMemo(
    () => ({
      ...(assistantYearMin ? { year_min: Number(assistantYearMin) } : {}),
      ...(assistantYearMax ? { year_max: Number(assistantYearMax) } : {}),
      ...(assistantOpenAccess ? { open_access: true } : {}),
    }),
    [assistantOpenAccess, assistantYearMax, assistantYearMin],
  );

  const downloadReport = async () => {
    if (!navigationQuestion.trim()) return;
    setExporting(true);
    try {
      const report = await exportEvidenceReport(cityMode, navigationQuestion.trim(), assistantFilters);
      const anchor = document.createElement('a');
      anchor.href = `data:text/markdown;charset=utf-8,${encodeURIComponent(report)}`;
      anchor.download = 'research-evidence-report.md';
      anchor.click();
    } finally {
      setExporting(false);
    }
  };

  const selectedBuilding = buildings.find((building) => building.building_id === selectedBuildingId) ?? null;
  const selectedBridge = bridges.find((bridge) => bridge.bridge_id === selectedBridgeId) ?? null;
  const selectedStreet = streets.find((street) => street.street_id === selectedStreetId) ?? null;
  const selectedPaper = interiorPapers.find((paper) => paper.paper_id === selectedPaperId) ?? null;
  const cityTitle = cityMode.startsWith('seeded') ? 'Seeded Research Graph City' : 'Research Graph City';
  const timelineMax = Math.max(1, ...(timeline?.years.map((item) => item.paper_count) ?? [1]));
  const comparisonCities = availableCities.filter((item) => item.city_type !== cityMode && item.status === 'ready');
  const domainLegend = useMemo(() => {
    const entries = new Map<string, { communityName: string; domainName: string; color: string }>();
    for (const community of communities) {
      const communityName = community.name || community.community_id;
      const domainName = community.semantic_domain_name ?? 'General Research';
      entries.set(community.community_id, { communityName, domainName, color: community.color });
    }
    for (const building of buildings) {
      const id = building.community_id ?? building.building_id;
      const communityName = building.top_labels[0] ?? building.building_id;
      const domainName = building.semantic_domain_name;
      const color = building.semantic_color;
      if (!domainName || !color || entries.has(id)) continue;
      entries.set(id, { communityName, domainName, color });
    }
    return [...entries.values()];
  }, [buildings, communities]);

  return (
    <main className="flex h-screen overflow-hidden bg-slate-100 text-slate-950 max-md:h-auto max-md:min-h-screen max-md:flex-col max-md:overflow-y-auto">
      <section data-testid="left-panel" className="flex h-screen w-72 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white p-5 max-md:h-[42vh] max-md:w-full max-md:border-b max-md:border-r-0">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Graph City</p>
          <h1 className="mt-1 text-2xl font-semibold">{cityTitle}</h1>
          <p className="mt-2 text-sm text-slate-600">OpenAlex research communities plotted as buildings, floors, and semantic bridges.</p>
        </div>
        <div className="mt-6 grid grid-cols-3 gap-2 text-sm">
          <Stat value={buildings.length.toString()} label="buildings" />
          <Stat value={bridges.length.toString()} label="bridges" />
          <Stat value={streets.length.toString()} label="streets" />
        </div>
        {domainLegend.length > 0 && (
          <div className="mt-5 rounded border border-slate-200 p-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Layers size={16} />
              Color scheme
            </div>
            <div className="mt-3 space-y-2">
              {domainLegend.slice(0, 8).map((item) => (
                <div key={`${item.communityName}-${item.color}`} className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="h-3 w-3 shrink-0 rounded-sm border border-slate-200" style={{ backgroundColor: item.color }} />
                  <span>
                    <span className="font-medium text-slate-700">{item.communityName}</span>
                    <span className="block text-slate-500">{item.domainName}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-5 rounded border border-slate-200 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles size={16} />
            Seeded city
          </div>
          <label htmlFor="seed-papers" className="mt-3 block text-xs font-semibold uppercase text-slate-500">
            Seed papers
          </label>
          <textarea
            id="seed-papers"
            className="mt-1 h-24 w-full resize-none rounded border border-slate-200 p-2 text-sm outline-none focus:border-slate-400"
            value={seedText}
            placeholder="One paper title, DOI, or OpenAlex URL per line"
            onChange={(event) => setSeedText(event.target.value)}
          />
          <p className={`mt-1 text-xs ${seedStats.unique > 30 ? 'text-red-600' : 'text-slate-500'}`}>
            {seedStats.entries} entries · {seedStats.unique} unique · {seedStats.duplicates} {seedStats.duplicates === 1 ? 'duplicate' : 'duplicates'}
          </p>
          <label htmlFor="target-papers" className="mt-3 block text-xs font-semibold uppercase text-slate-500">
            Target papers
          </label>
          <select
            id="target-papers"
            className="mt-1 w-full rounded border border-slate-200 bg-white p-2 text-sm outline-none focus:border-slate-400"
            value={targetPaperCount}
            onChange={(event) => setTargetPaperCount(Number(event.target.value))}
          >
            {[1000, 10000, 25000, 50000, 100000].map((value) => (
              <option key={value} value={value}>{value.toLocaleString()}</option>
            ))}
          </select>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button
              type="button"
              className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              disabled={['creating', 'queued', 'building'].includes(seedBuildStatus) || !seedInputValid}
              onClick={() => void buildSeededCity(seedText, targetPaperCount)}
            >
              {['creating', 'queued', 'building'].includes(seedBuildStatus) ? 'Building...' : 'Build Seeded City'}
            </button>
            <button
              type="button"
              className="rounded border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50"
              onClick={() => setSeedText(sampleSeedPapers)}
            >
              Use sample
            </button>
          </div>
          <button
            type="button"
            className="mt-2 w-full rounded border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50"
            onClick={() => void loadCity('research')}
          >
            Research City
          </button>
          <button
            type="button"
            className="mt-2 w-full rounded border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50"
            onClick={() => void loadCity('seeded')}
          >
            Open Seeded City
          </button>
          {seedBuildMessage && (
            <p className={`mt-2 text-xs ${seedBuildStatus === 'error' ? 'text-red-600' : 'text-slate-500'}`}>{seedBuildMessage}</p>
          )}
          {seedBuildJob && (
            <div className="mt-2" aria-label="Build progress">
              <div className="flex justify-between text-xs text-slate-500">
                <span>{seedBuildJob.stage.replaceAll('_', ' ')}</span>
                <span>{seedBuildJob.progress_current.toLocaleString()} of {seedBuildJob.progress_total.toLocaleString()} papers</span>
              </div>
              <progress className="mt-1 h-2 w-full" max={Math.max(seedBuildJob.progress_total, 1)} value={seedBuildJob.progress_current} />
            </div>
          )}
          {seedGraph && (seedGraph.nodes.length > 0 || seedGraph.unresolved.length > 0) && (
            <div className="mt-3 border-t border-slate-200 pt-3 text-xs">
              <p className="font-semibold uppercase text-slate-500">Resolved seed graph</p>
              <p className="mt-1 text-slate-500">{seedGraph.nodes.length} papers · {seedGraph.edges.length} seed relationships</p>
              <div className="mt-2 space-y-1">
                {seedGraph.nodes.slice(0, 10).map((node) => (
                  <p key={node.paper_id} className="line-clamp-2 text-slate-700">{node.title}</p>
                ))}
              </div>
              {seedGraph.unresolved.length > 0 && (
                <p className="mt-2 text-red-600">Unresolved: {seedGraph.unresolved.join(' · ')}</p>
              )}
            </div>
          )}
          {['queued', 'building'].includes(seedBuildStatus) && (
            <button
              type="button"
              className="mt-2 w-full rounded border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
              onClick={() => void cancelSeedBuild()}
            >
              Cancel build
            </button>
          )}
        </div>
        <div className="mt-5 rounded border border-slate-200 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Compass size={16} />
            Research assistant
          </div>
          <label htmlFor="city-navigation-question" className="mt-3 block text-xs font-semibold uppercase text-slate-500">
            Research question
          </label>
          <textarea
            id="city-navigation-question"
            className="mt-1 h-20 w-full resize-none rounded border border-slate-200 p-2 text-sm outline-none focus:border-slate-400"
            value={navigationQuestion}
            placeholder="Ask about domains, papers, authors, methods, datasets, or connections"
            onChange={(event) => setNavigationQuestion(event.target.value)}
          />
          <details className="mt-2 rounded border border-slate-200 bg-white px-2 py-1.5">
            <summary className="cursor-pointer text-xs font-medium text-slate-600">Filters</summary>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <label className="text-[11px] text-slate-500">
                From year
                <input
                  aria-label="Assistant from year"
                  inputMode="numeric"
                  className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-slate-800"
                  value={assistantYearMin}
                  onChange={(event) => setAssistantYearMin(event.target.value.replace(/\D/g, '').slice(0, 4))}
                />
              </label>
              <label className="text-[11px] text-slate-500">
                To year
                <input
                  aria-label="Assistant to year"
                  inputMode="numeric"
                  className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs text-slate-800"
                  value={assistantYearMax}
                  onChange={(event) => setAssistantYearMax(event.target.value.replace(/\D/g, '').slice(0, 4))}
                />
              </label>
            </div>
            <label className="mt-2 flex cursor-pointer items-center justify-between text-xs text-slate-600">
              Open access only
              <input type="checkbox" checked={assistantOpenAccess} onChange={(event) => setAssistantOpenAccess(event.target.checked)} />
            </label>
          </details>
          <button
            type="button"
            className="mt-2 w-full rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={navigationStatus === 'asking' || navigationQuestion.trim().length === 0 || buildings.length === 0}
            onClick={() => void askCityNavigator(navigationQuestion, assistantFilters)}
          >
            {navigationStatus === 'asking' ? 'Searching evidence...' : 'Ask Research City'}
          </button>
          {navigationError && <p className="mt-2 text-xs text-red-600">{navigationError}</p>}
          {navigationResponse && (
            <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
              <p className="leading-5">{navigationResponse.answer_markdown}</p>
              {!navigationResponse.model_available && (
                <p className="mt-1 text-slate-500">Showing PostgreSQL retrieval results without LLM synthesis.</p>
              )}
              {navigationResponse.claims.length > 0 && (
                <div className="mt-2 space-y-2 border-t border-slate-200 pt-2">
                  {navigationResponse.claims.slice(0, 5).map((claim, index) => (
                    <div key={`${claim.claim}-${index}`}>
                      <p>{claim.claim}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {claim.citation_ids.map((citationId) => (
                          <button
                            key={citationId}
                            type="button"
                            className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] hover:border-amber-400 hover:bg-amber-50"
                            onClick={() => {
                              const paper = navigationResponse.papers.find((item) => item.evidence_id === citationId);
                              const building = navigationResponse.buildings.find((item) => item.evidence_id === citationId);
                              const relationship = navigationResponse.relationships.find((item) => item.evidence_id === citationId);
                              if (paper?.building_id) selectBuilding(paper.building_id);
                              if (building?.building_id) selectBuilding(building.building_id);
                              if (relationship?.relationship_kind === 'bridge') selectBridge(relationship.relationship_id);
                              if (relationship?.relationship_kind === 'street') selectStreet(relationship.relationship_id);
                            }}
                          >
                            {citationId}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {navigationResponse.districts.length > 0 && (
                <div className="mt-2">
                  <p className="font-semibold uppercase text-slate-500">Domains</p>
                  <p className="mt-1">{navigationResponse.districts.map((item) => item.domain_name || item.name).filter(Boolean).join(' · ')}</p>
                </div>
              )}
              {navigationResponse.papers.length > 0 && (
                <div className="mt-2 space-y-1">
                  <p className="font-semibold uppercase text-slate-500">Evidence papers</p>
                  {navigationResponse.papers.slice(0, 6).map((paper) => (
                    <button
                      key={paper.evidence_id}
                      type="button"
                      className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-left hover:border-amber-400 hover:bg-amber-50"
                      onClick={() => {
                        if (paper.building_id) selectBuilding(paper.building_id);
                      }}
                    >
                      <span className="font-medium text-slate-800">{paper.title}</span>
                      <span className="block text-slate-500">
                        {[paper.publication_year, paper.venue, paper.building_label].filter(Boolean).join(' · ')}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {navigationResponse.relationships.length > 0 && (
                <div className="mt-2 space-y-1">
                  <p className="font-semibold uppercase text-slate-500">Relationships</p>
                  {navigationResponse.relationships.slice(0, 4).map((relationship) => (
                    <button
                      key={relationship.evidence_id}
                      type="button"
                      className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-left hover:bg-slate-50"
                      onClick={() => {
                        if (relationship.relationship_kind === 'bridge') selectBridge(relationship.relationship_id);
                        if (relationship.relationship_kind === 'street') selectStreet(relationship.relationship_id);
                      }}
                    >
                      <span className="font-medium">{relationship.source_building_id} to {relationship.target_building_id}</span>
                      <span className="block text-slate-500">{relationship.relationship_kind} · score {relationship.score.toFixed(2)}</span>
                    </button>
                  ))}
                </div>
              )}
              {navigationResponse.route_steps.length > 0 && (
                <div className="mt-2 space-y-1">
                  {navigationResponse.route_steps.slice(0, 5).map((step, index) => (
                    <button
                      key={`${step.target_type}-${step.target_id}-${index}`}
                      type="button"
                      aria-label={`Navigator step ${index + 1}: ${step.label}`}
                      className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-left hover:bg-slate-50"
                      onClick={() => {
                        if (step.target_type === 'building') selectBuilding(step.target_id);
                        if (step.target_type === 'bridge') selectBridge(step.target_id);
                        if (step.target_type === 'street') selectStreet(step.target_id);
                        if (step.target_type === 'paper') {
                          const paper = navigationResponse.papers.find((item) => item.paper_id === step.target_id);
                          if (paper?.building_id) selectBuilding(paper.building_id);
                        }
                      }}
                    >
                      <span className="font-medium">
                        {step.target_id} · {step.label}
                      </span>
                      <span className="block text-slate-500">{step.reason}</span>
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                className="mt-2 flex w-full items-center justify-center gap-1 rounded border border-slate-200 bg-white px-2 py-1.5 font-medium hover:bg-slate-50 disabled:text-slate-400"
                disabled={exporting}
                onClick={() => void downloadReport()}
              >
                <Download size={13} />
                {exporting ? 'Preparing...' : 'Export evidence'}
              </button>
            </div>
          )}
        </div>
        {(timeline || comparisonCities.length > 0) && (
          <div className="mt-5 rounded border border-slate-200 p-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Activity size={16} />
              Analysis
            </div>
            {timeline && timeline.years.length > 0 && (
              <div className="mt-3">
                <div className="flex justify-between text-[11px] text-slate-500">
                  <span>{timeline.year_min}</span>
                  <span>Publication timeline</span>
                  <span>{timeline.year_max}</span>
                </div>
                <div className="mt-1 flex h-10 items-end gap-px" aria-label="Publication timeline">
                  {timeline.years.map((item) => (
                    <span
                      key={item.year}
                      title={`${item.year}: ${item.paper_count} papers`}
                      className="min-w-px flex-1 bg-cyan-500"
                      style={{ height: `${Math.max(8, (item.paper_count / timelineMax) * 100)}%` }}
                    />
                  ))}
                </div>
              </div>
            )}
            {comparisonCities.length > 0 && (
              <div className="mt-3 border-t border-slate-200 pt-3">
                <select
                  aria-label="Comparison city"
                  className="w-full rounded border border-slate-200 bg-white p-1.5 text-xs"
                  value={compareCityId}
                  onChange={(event) => setCompareCityId(event.target.value)}
                >
                  <option value="">Compare with...</option>
                  {comparisonCities.map((city) => (
                    <option key={city.city_type} value={city.city_type}>{city.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="mt-2 w-full rounded border border-slate-200 px-2 py-1.5 text-xs font-medium hover:bg-slate-50 disabled:text-slate-400"
                  disabled={!compareCityId}
                  onClick={() => void compareCities(cityMode, compareCityId).then(setComparison)}
                >
                  Compare cities
                </button>
                {comparison && (
                  <div className="mt-2 text-xs text-slate-600">
                    <p><span className="font-semibold text-slate-800">{comparison.papers.shared.toLocaleString()}</span> shared papers</p>
                    <p>{comparison.papers.left_only.toLocaleString()} current-only · {comparison.papers.right_only.toLocaleString()} comparison-only</p>
                    {comparison.domains.shared.length > 0 && <p className="mt-1">Shared: {comparison.domains.shared.join(', ')}</p>}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        <div className="mt-6 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{interiorActive ? 'Interior layers' : 'Layers'}</h2>
          {interiorActive ? (
            <>
              {(
                [
                  ['nodes', 'Paper nodes'],
                  ['edges', 'Internal edges'],
                  ['labels', 'Paper labels'],
                  ['floors', 'Floor rings'],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="flex cursor-pointer items-center justify-between rounded border border-slate-200 px-3 py-2 text-sm">
                  <span>{label}</span>
                  <input type="checkbox" aria-label={label} checked={interiorLayers[key]} onChange={() => toggleInteriorLayer(key)} />
                </label>
              ))}
              <button
                type="button"
                className="w-full rounded border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50"
                onClick={() => exitBuildingInterior()}
              >
                Exit to city
              </button>
            </>
          ) : (
            layerLabels.map(([key, label, icon]) => (
              <label key={key} className="flex cursor-pointer items-center justify-between rounded border border-slate-200 px-3 py-2 text-sm">
                <span className="flex items-center gap-2">
                  {icon}
                  {label}
                </span>
                <input type="checkbox" aria-label={label} checked={layers[key]} onChange={() => toggleLayer(key)} />
              </label>
            ))
          )}
        </div>
        <div className="mt-6 pb-6">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Buildings</h2>
          <div className="space-y-2">
            {buildings.map((building) => {
              const selected = building.building_id === selectedBuildingId;
              return (
                <button
                  key={building.building_id}
                  className={`w-full rounded border px-3 py-2 text-left text-sm ${
                    selected ? 'border-amber-400 bg-amber-50 shadow-sm' : 'border-slate-200 hover:bg-slate-50'
                  }`}
                  onClick={() => selectBuilding(building.building_id)}
                >
                  <span className="font-medium">{building.building_id}</span>
                  <span className="block truncate text-slate-500">{building.top_labels.join(', ')}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>
      <section className="relative min-w-0 flex-1 max-md:h-[58vh] max-md:w-full max-md:flex-none">
        {loading && <Overlay text={`Loading ${cityTitle}`} />}
        {error && <Overlay text={error} />}
        {interiorActive && interiorLoading && <Overlay text="Entering building..." />}
        {interiorActive && !interiorLoading && !interiorError && (
          <Overlay text={`Inside ${selectedBuildingId ?? 'building'} · ${interiorPapers.length} papers`} />
        )}
        {interiorActive && !interiorLoading && !interiorError && (
          <div className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2">
            <div className="rounded border border-slate-200 bg-white/95 px-3 py-2 text-xs text-slate-600 shadow">
              Interior graph · {interiorPapers.length} papers · {Math.min(interiorEdges.length, 220)} strongest edges
            </div>
            {selectedPaperId && (
              <button
                type="button"
                className="rounded border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow hover:bg-slate-50"
                onClick={() => selectPaper(null)}
              >
                Unselect paper
              </button>
            )}
          </div>
        )}
        <CityScene
          buildings={buildings}
          bridges={bridges}
          streets={streets}
          communities={communities}
          layers={layers}
          selectedBuildingId={selectedBuildingId}
          selectedBridgeId={selectedBridgeId}
          selectedStreetId={selectedStreetId}
          selectedPaperId={selectedPaperId}
          interiorActive={interiorActive}
          interiorPapers={interiorPapers}
          interiorEdges={interiorEdges}
          interiorLayers={interiorLayers}
          onSelectBuilding={selectBuilding}
          onSelectBridge={selectBridge}
          onSelectStreet={selectStreet}
          onSelectPaper={selectPaper}
        />
      </section>
      <Inspector
        cityType={cityMode}
        building={selectedBuilding}
        bridge={selectedBridge}
        street={selectedStreet}
        selectedPaper={selectedPaper}
        interiorEdges={interiorEdges}
        interiorActive={interiorActive}
        interiorLoading={interiorLoading}
        interiorError={interiorError}
        onEnterInterior={() => void enterBuildingInterior()}
        onExitInterior={exitBuildingInterior}
        onSelectPaper={selectPaper}
      />
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded border border-slate-200 p-3">
      <div className="text-xl font-semibold">{value}</div>
      <div className="text-sm text-slate-500">{label}</div>
      <span className="sr-only">
        {value} {label}
      </span>
    </div>
  );
}

function Overlay({ text }: { text: string }) {
  return <div className="absolute left-4 top-4 z-10 rounded bg-white px-4 py-2 text-sm shadow">{text}</div>;
}
