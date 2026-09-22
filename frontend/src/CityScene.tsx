import { Html, Line, OrbitControls } from '@react-three/drei';
import { Canvas, useThree } from '@react-three/fiber';
import type { MutableRefObject } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';

import { fitInteriorCamera } from './interiorCamera';
import { layoutInteriorNodes, strongestInteriorEdges } from './interiorLayout';
import { pickInteriorPaperId } from './interiorPicking';
import { bridgeOpacity, bridgeWidth, buildingMaterial, floorHeight, floorMaterial, selectedHighlight } from './visualMapping';
import { normalizeCityLayout } from './sceneLayout';
import type {
  Bridge,
  Building,
  Community,
  InteriorLayerState,
  LayerState,
  ResearchEdgeDetail,
  ResearchPaper,
  Street,
} from './types';
import type { InteriorNodePosition } from './interiorLayout';

const MIN_CAMERA_DISTANCE = 90;
const MAX_CAMERA_DISTANCE = 620;
const INTERIOR_MIN_DISTANCE = 45;
const INTERIOR_MAX_DISTANCE = 520;

interface CitySceneProps {
  buildings: Building[];
  bridges: Bridge[];
  streets: Street[];
  communities: Community[];
  layers: LayerState;
  selectedBuildingId: string | null;
  selectedBridgeId: string | null;
  selectedStreetId: string | null;
  selectedPaperId: string | null;
  interiorActive: boolean;
  interiorPapers: ResearchPaper[];
  interiorEdges: ResearchEdgeDetail[];
  interiorLayers: InteriorLayerState;
  onSelectBuilding: (id: string) => void;
  onSelectBridge: (id: string) => void;
  onSelectStreet: (id: string) => void;
  onSelectPaper: (id: string | null) => void;
}

export function CityScene(props: CitySceneProps) {
  const cameraPosition: [number, number, number] = props.interiorActive ? [0, 110, 210] : [0, 260, 430];
  return (
    <Canvas key={props.interiorActive ? `interior-${props.selectedBuildingId}` : 'city'} camera={{ position: cameraPosition, fov: 48 }} shadows>
      <color attach="background" args={[props.interiorActive ? '#e8eef5' : '#eef4f7']} />
      <ambientLight intensity={0.65} />
      <directionalLight position={[120, 220, 160]} intensity={1.1} castShadow />
      {!props.interiorActive && <Grid />}
      {props.interiorActive ? <BuildingInterior {...props} /> : <CityContent {...props} />}
      <CameraRig interior={props.interiorActive} />
    </Canvas>
  );
}

function CameraRig({ interior }: { interior: boolean }) {
  const controlsRef = useRef<any>(null);
  return (
    <>
      <OrbitControls
        ref={controlsRef}
        makeDefault
        enableZoom
        zoomSpeed={1.1}
        minPolarAngle={Math.PI / 8}
        maxPolarAngle={Math.PI / 2.35}
        minDistance={interior ? INTERIOR_MIN_DISTANCE : MIN_CAMERA_DISTANCE}
        maxDistance={interior ? INTERIOR_MAX_DISTANCE : MAX_CAMERA_DISTANCE}
        target={interior ? [0, 36, 0] : [0, 0, 0]}
      />
      <ZoomHud controlsRef={controlsRef} interior={interior} />
    </>
  );
}

function ZoomHud({ controlsRef, interior }: { controlsRef: MutableRefObject<any>; interior: boolean }) {
  const { camera } = useThree();
  const zoom = (factor: number) => {
    const min = interior ? INTERIOR_MIN_DISTANCE : MIN_CAMERA_DISTANCE;
    const max = interior ? INTERIOR_MAX_DISTANCE : MAX_CAMERA_DISTANCE;
    const controls = controlsRef.current;
    const target = controls?.target ?? new THREE.Vector3(0, 0, 0);
    const offset = camera.position.clone().sub(target);
    const nextDistance = Math.min(max, Math.max(min, offset.length() * factor));
    offset.setLength(nextDistance);
    camera.position.copy(target).add(offset);
    controls?.update();
  };
  return (
    <Html fullscreen style={{ pointerEvents: 'none' }}>
      <div className="pointer-events-none absolute right-4 top-4 flex flex-col gap-2">
        <button className="pointer-events-auto h-9 w-9 rounded border border-slate-200 bg-white text-lg font-semibold shadow" aria-label="Zoom in" onClick={() => zoom(0.82)}>
          +
        </button>
        <button className="pointer-events-auto h-9 w-9 rounded border border-slate-200 bg-white text-lg font-semibold shadow" aria-label="Zoom out" onClick={() => zoom(1.22)}>
          -
        </button>
      </div>
    </Html>
  );
}

function BuildingInterior({
  buildings,
  selectedBuildingId,
  selectedPaperId,
  interiorPapers,
  interiorEdges,
  interiorLayers,
  onSelectPaper,
}: CitySceneProps) {
  const [hoveredPaperId, setHoveredPaperId] = useState<string | null>(null);
  const building = buildings.find((item) => item.building_id === selectedBuildingId) ?? null;
  const positions = useMemo(() => layoutInteriorNodes(interiorPapers, building?.floors ?? []), [building?.floors, interiorPapers]);
  const positionById = useMemo(() => Object.fromEntries(positions.map((node) => [node.paperId, node])), [positions]);
  const paperById = useMemo(() => Object.fromEntries(interiorPapers.map((paper) => [paper.paper_id, paper])), [interiorPapers]);
  const visibleEdges = useMemo(() => strongestInteriorEdges(interiorEdges), [interiorEdges]);
  const floorBands = useMemo(() => {
    const indices = [...new Set(positions.map((node) => node.floorIndex))].sort((a, b) => a - b);
    return indices;
  }, [positions]);
  const tooltipPaperId = hoveredPaperId;
  const tooltipPaper = tooltipPaperId ? paperById[tooltipPaperId] : null;
  const tooltipPosition = tooltipPaperId ? positionById[tooltipPaperId] : null;

  return (
    <group>
      <InteriorCameraFit positions={positions} />
      <InteriorScreenPicker positions={positions} onHover={setHoveredPaperId} onSelect={onSelectPaper} />
      {interiorLayers.floors &&
        floorBands.map((floorIndex) => (
          <mesh
            key={`floor-${floorIndex}`}
            position={[0, floorIndex * 22 + 0.2, 0]}
            rotation={[-Math.PI / 2, 0, 0]}
            raycast={() => null}
          >
            <ringGeometry args={[12, 58, 48]} />
            <meshStandardMaterial color="#cbd5e1" transparent opacity={0.28} side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
        ))}
      {interiorLayers.edges &&
        visibleEdges.map((edge) => {
          const source = positionById[edge.source];
          const target = positionById[edge.target];
          if (!source || !target) return null;
          const highlighted =
            selectedPaperId === edge.source ||
            selectedPaperId === edge.target ||
            hoveredPaperId === edge.source ||
            hoveredPaperId === edge.target;
          return (
            <Line
              key={`${edge.source}-${edge.target}-${edge.edge_weight}`}
              points={[
                [source.x, source.y, source.z],
                [target.x, target.y, target.z],
              ]}
              color={highlighted ? '#f59e0b' : '#64748b'}
              lineWidth={highlighted ? 2.4 : Math.max(0.8, edge.edge_weight * 2.2)}
              transparent
              opacity={highlighted ? 0.95 : 0.28 + edge.edge_weight * 0.45}
              raycast={() => null}
            />
          );
        })}
      {interiorLayers.nodes &&
        positions.map((node) => {
          const paper = paperById[node.paperId];
          if (!paper) return null;
          return (
            <InteriorNode
              key={node.paperId}
              paper={paper}
              position={node}
              selected={selectedPaperId === node.paperId}
              hovered={hoveredPaperId === node.paperId}
            />
          );
        })}
      {tooltipPaper && tooltipPosition && (
        <Html position={[tooltipPosition.x, tooltipPosition.y + 5, tooltipPosition.z]} center zIndexRange={[50, 0]} style={{ pointerEvents: 'none' }}>
          <div className="pointer-events-none max-w-56 rounded border border-slate-200 bg-white/95 px-2 py-1 text-center text-[11px] leading-tight text-slate-800 shadow">
            <div className="font-semibold">{tooltipPaper.title}</div>
            <div className="mt-0.5 text-slate-500">
              {[tooltipPaper.publication_year, tooltipPaper.citation_count !== undefined ? `${tooltipPaper.citation_count} cites` : null]
                .filter(Boolean)
                .join(' · ')}
            </div>
          </div>
        </Html>
      )}
    </group>
  );
}

/** Pull the camera back so the full interior graph fits on screen. */
function InteriorCameraFit({ positions }: { positions: InteriorNodePosition[] }) {
  const camera = useThree((state) => state.camera);
  const controls = useThree((state) => state.controls) as null | {
    target: THREE.Vector3;
    update: () => void;
    minDistance?: number;
    maxDistance?: number;
  };
  const fittedFor = useRef('');

  useEffect(() => {
    if (!positions.length || !controls || !(camera instanceof THREE.PerspectiveCamera)) return;
    const key = `${positions.length}:${positions[0]?.paperId}:${positions[positions.length - 1]?.paperId}:${positions.reduce((sum, node) => sum + node.y, 0).toFixed(1)}`;
    if (fittedFor.current === key) return;
    fittedFor.current = key;
    fitInteriorCamera(camera, controls, positions, {
      padding: 16,
      minDistance: INTERIOR_MIN_DISTANCE,
      maxDistance: INTERIOR_MAX_DISTANCE,
    });
  }, [camera, controls, positions]);

  return null;
}

/** Screen-space + ray picker; empty clicks clear the selection. */
function InteriorScreenPicker({
  positions,
  onHover,
  onSelect,
}: {
  positions: InteriorNodePosition[];
  onHover: (id: string | null) => void;
  onSelect: (id: string | null) => void;
}) {
  const { camera, gl } = useThree();
  const positionsRef = useRef(positions);
  const pointerDownRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    positionsRef.current = positions;
  }, [positions]);

  useEffect(() => {
    const element = gl.domElement;

    const pickFromEvent = (event: PointerEvent) => {
      const rect = element.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      // Use CSS pixel space from the canvas rect (avoids DPR / R3F size mismatches).
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      return pickInteriorPaperId(positionsRef.current, camera, { width: rect.width, height: rect.height }, x, y, 44);
    };

    const onPointerMove = (event: PointerEvent) => {
      const id = pickFromEvent(event);
      onHover(id);
      element.style.cursor = id ? 'pointer' : 'auto';
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      pointerDownRef.current = { x: event.clientX, y: event.clientY };
    };

    const onPointerUp = (event: PointerEvent) => {
      if (event.button !== 0 || !pointerDownRef.current) return;
      const dx = event.clientX - pointerDownRef.current.x;
      const dy = event.clientY - pointerDownRef.current.y;
      pointerDownRef.current = null;
      // Ignore drags used for orbiting the camera.
      if (Math.hypot(dx, dy) > 6) return;
      const id = pickFromEvent(event);
      onSelect(id);
    };

    const onPointerLeave = () => {
      pointerDownRef.current = null;
      onHover(null);
      element.style.cursor = 'auto';
    };

    element.addEventListener('pointermove', onPointerMove);
    element.addEventListener('pointerdown', onPointerDown);
    element.addEventListener('pointerup', onPointerUp);
    element.addEventListener('pointerleave', onPointerLeave);
    return () => {
      element.removeEventListener('pointermove', onPointerMove);
      element.removeEventListener('pointerdown', onPointerDown);
      element.removeEventListener('pointerup', onPointerUp);
      element.removeEventListener('pointerleave', onPointerLeave);
      element.style.cursor = 'auto';
    };
  }, [camera, gl, onHover, onSelect]);

  return null;
}

function InteriorNode({
  paper,
  position,
  selected,
  hovered,
}: {
  paper: ResearchPaper;
  position: { x: number; y: number; z: number };
  selected: boolean;
  hovered: boolean;
}) {
  const radius = 1.2 + Math.min(2.4, Math.log10((paper.citation_count ?? 0) + 10));
  return (
    <group position={[position.x, position.y, position.z]}>
      <mesh raycast={() => null}>
        <sphereGeometry args={[radius, 18, 18]} />
        <meshStandardMaterial
          color={selected ? selectedHighlight.color : hovered ? '#38bdf8' : '#0f766e'}
          emissive={selected ? selectedHighlight.emissive : hovered ? '#0284c7' : '#115e59'}
          emissiveIntensity={selected ? 0.85 : hovered ? 0.45 : 0.15}
        />
      </mesh>
    </group>
  );
}

function CityContent({
  buildings,
  bridges,
  streets,
  communities,
  layers,
  selectedBuildingId,
  selectedBridgeId,
  selectedStreetId,
  onSelectBuilding,
  onSelectBridge,
  onSelectStreet,
}: CitySceneProps) {
  const canvasWidth = useThree((state) => state.size.width);
  const layoutBuildings = useMemo(() => normalizeCityLayout(buildings), [buildings]);
  const communityColors = useMemo(
    () => Object.fromEntries(communities.map((community) => [community.community_id, community.color])),
    [communities],
  );
  const buildingById = useMemo(() => Object.fromEntries(layoutBuildings.map((building) => [building.building_id, building])), [layoutBuildings]);
  const visibleLabelIds = useMemo(() => {
    const budget = canvasWidth < 520 ? 6 : canvasWidth < 900 ? 9 : layoutBuildings.length;
    const ids = new Set(
      [...layoutBuildings]
        .sort((left, right) => right.node_count - left.node_count || left.building_id.localeCompare(right.building_id))
        .slice(0, budget)
        .map((building) => building.building_id),
    );
    if (selectedBuildingId) ids.add(selectedBuildingId);
    return ids;
  }, [canvasWidth, layoutBuildings, selectedBuildingId]);
  return (
    <group>
      {layers.streets &&
        streets.map((street) => {
          const source = buildingById[street.source_building_id];
          const target = buildingById[street.target_building_id];
          if (!source || !target) return null;
          return (
            <StreetRoad
              key={street.street_id}
              street={street}
              source={source}
              target={target}
              selected={street.street_id === selectedStreetId}
              onSelect={onSelectStreet}
            />
          );
        })}
      {layers.bridges &&
        bridges.map((bridge) => {
          const source = buildingById[bridge.source_building_id];
          const target = buildingById[bridge.target_building_id];
          if (!source || !target) return null;
          return (
            <BridgeRoad
              key={bridge.bridge_id}
              bridge={bridge}
              source={source}
              target={target}
              selected={bridge.bridge_id === selectedBridgeId}
              onSelect={onSelectBridge}
            />
          );
        })}
      {layers.buildings &&
        layoutBuildings.map((building) => (
          <BuildingMesh
            key={building.building_id}
            building={building}
            communityColors={communityColors}
            showFloors={layers.floors}
            showLabels={layers.labels && visibleLabelIds.has(building.building_id)}
            showActivation={layers.activation}
            selected={building.building_id === selectedBuildingId}
            onSelect={onSelectBuilding}
          />
        ))}
    </group>
  );
}

function BuildingMesh({
  building,
  communityColors,
  showFloors,
  showLabels,
  showActivation,
  selected,
  onSelect,
}: {
  building: Building;
  communityColors: Record<string, string>;
  showFloors: boolean;
  showLabels: boolean;
  showActivation: boolean;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const [hovered, setHovered] = useState(false);
  const material = buildingMaterial(building, communityColors);
  const levels = showFloors && building.floors.length > 0 ? building.floors : [{ floor_id: `${building.building_id}_single` }];
  const segmentHeight = floorHeight({ ...building, floors: levels });
  const radius = building.footprint / 2;
  return (
    <group position={[building.x, 0, building.z]}>
      {selected && <SelectionRing radius={radius * 1.15} y={0.85} />}
      {levels.map((floor, index) => {
        const y = segmentHeight * index + segmentHeight / 2;
        const levelMaterial = floorMaterial(building, floor, index, levels.length, communityColors);
        return (
          <mesh
            key={floor.floor_id}
            position={[0, y, 0]}
            castShadow
            receiveShadow
            onClick={(event) => {
              event.stopPropagation();
              onSelect(building.building_id);
            }}
            onPointerEnter={(event) => {
              event.stopPropagation();
              setHovered(true);
            }}
            onPointerLeave={() => setHovered(false)}
          >
            <cylinderGeometry args={[radius * 0.82, radius, segmentHeight * 0.96, 24]} />
            <meshStandardMaterial
              color={levelMaterial.color}
              emissive={material.emissive}
              emissiveIntensity={showActivation ? material.emissiveIntensity : 0}
              transparent
              opacity={material.opacity}
            />
          </mesh>
        );
      })}
      {showLabels && (
        <Html position={[0, building.height + 12, 0]} center zIndexRange={[20, 0]}>
          <div
            className={`pointer-events-none max-w-44 rounded border bg-white/95 px-2 py-1 text-center text-xs font-semibold leading-tight text-slate-800 shadow ${
              selected ? 'border-amber-400 ring-2 ring-amber-300' : 'border-slate-200'
            }`}
          >
            {building.top_labels[0] ?? building.building_id}
          </div>
        </Html>
      )}
      {hovered && (
        <Html position={[0, building.height + 18, 0]} center>
          <div className="rounded border border-slate-200 bg-white px-3 py-2 text-xs shadow">
            <div className="font-semibold">{building.building_id}</div>
            <div>{building.node_count} papers</div>
            <div>density {building.internal_density.toFixed(2)}</div>
          </div>
        </Html>
      )}
    </group>
  );
}

function StreetRoad({
  street,
  source,
  target,
  selected,
  onSelect,
}: {
  street: Street;
  source: Building;
  target: Building;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const midX = (source.x + target.x) / 2;
  const midZ = (source.z + target.z) / 2;
  const dx = target.x - source.x;
  const dz = target.z - source.z;
  const length = Math.sqrt(dx * dx + dz * dz);
  const angle = Math.atan2(dx, dz);
  const width = 2.5 + street.street_score * 4;
  const opacity = Math.min(0.45, 0.22 + street.street_score * 0.35);
  return (
    <group>
      {selected && <RoadHighlight midX={midX} midZ={midZ} y={1.15} angle={angle} length={length} width={width + 4} />}
      {selected && (
        <>
          <SelectionRing radius={source.footprint * 0.62} x={source.x} z={source.z} y={1.05} />
          <SelectionRing radius={target.footprint * 0.62} x={target.x} z={target.z} y={1.05} />
        </>
      )}
      <mesh
        position={[midX, 0.75, midZ]}
        rotation={[0, angle, 0]}
        onClick={(event) => {
          event.stopPropagation();
          onSelect(street.street_id);
        }}
      >
        <boxGeometry args={[width, 0.8, length]} />
        <meshStandardMaterial color="#4b5f62" transparent opacity={opacity} />
      </mesh>
    </group>
  );
}

function BridgeRoad({
  bridge,
  source,
  target,
  selected,
  onSelect,
}: {
  bridge: Bridge;
  source: Building;
  target: Building;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const midX = (source.x + target.x) / 2;
  const midZ = (source.z + target.z) / 2;
  const dx = target.x - source.x;
  const dz = target.z - source.z;
  const length = Math.sqrt(dx * dx + dz * dz);
  const angle = Math.atan2(dx, dz);
  const width = bridgeWidth(bridge);
  return (
    <group>
      {selected && <RoadHighlight midX={midX} midZ={midZ} y={2.25} angle={angle} length={length} width={width + 5} />}
      {selected && (
        <>
          <SelectionRing radius={source.footprint * 0.62} x={source.x} z={source.z} y={1.05} />
          <SelectionRing radius={target.footprint * 0.62} x={target.x} z={target.z} y={1.05} />
        </>
      )}
      <mesh
        position={[midX, 1.5, midZ]}
        rotation={[0, angle, 0]}
        onClick={(event) => {
          event.stopPropagation();
          onSelect(bridge.bridge_id);
        }}
      >
        <boxGeometry args={[width, 2, length]} />
        <meshStandardMaterial color="#364152" transparent opacity={bridgeOpacity(bridge)} emissive="#7cc7ff" emissiveIntensity={bridge.activation_score} />
      </mesh>
    </group>
  );
}

function SelectionRing({ radius, x = 0, y, z = 0 }: { radius: number; x?: number; y: number; z?: number }) {
  return (
    <mesh position={[x, y, z]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[radius, Math.max(0.45, radius * 0.08), 12, 48]} />
      <meshStandardMaterial color={selectedHighlight.color} emissive={selectedHighlight.emissive} emissiveIntensity={selectedHighlight.emissiveIntensity} transparent opacity={selectedHighlight.opacity} />
    </mesh>
  );
}

function RoadHighlight({ midX, midZ, y, angle, length, width }: { midX: number; midZ: number; y: number; angle: number; length: number; width: number }) {
  return (
    <mesh position={[midX, y, midZ]} rotation={[0, angle, 0]}>
      <boxGeometry args={[width, 0.7, length]} />
      <meshStandardMaterial color={selectedHighlight.color} emissive={selectedHighlight.emissive} emissiveIntensity={0.75} transparent opacity={0.58} />
    </mesh>
  );
}

function Grid() {
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[720, 720]} />
        <meshStandardMaterial color="#dce7df" />
      </mesh>
      <gridHelper args={[720, 24, '#8aa0a8', '#c0ced0']} position={[0, 0.2, 0]} />
    </>
  );
}
