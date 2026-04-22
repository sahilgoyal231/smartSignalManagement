"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import {
    Layers,
    Car,
    Radio,
    AlertTriangle,
    Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEffect } from "react";
import { MockVehicle, MockNode, VehicleType, NodeStatus } from "@/components/map/LeafletMap";
import LiveFeed from "@/components/map/LiveFeed";
import type { FilterMode } from "@/components/map/LeafletMap";

// ── Dynamically import the map (no SSR — leaflet is browser-only) ────────────
const LeafletMap = dynamic(() => import("@/components/map/LeafletMap"), {
    ssr: false,
    loading: () => (
        <div className="w-full h-full flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-dark-text-muted text-sm">Loading map…</p>
            </div>
        </div>
    ),
});

// ── Filter button data ─────────────────────────────────────────────────────────
const FILTERS: { label: string; value: FilterMode; icon: React.FC<{ className?: string }> }[] = [
    { label: "All",      value: "ALL",      icon: Layers },
    { label: "Vehicles", value: "VEHICLES", icon: Car    },
    { label: "Nodes",    value: "NODES",    icon: Radio  },
];

// ── Legend items ───────────────────────────────────────────────────────────────
const LEGEND = [
    { color: "#22c55e", label: "Node: Active"     },
    { color: "#ef4444", label: "Node: Preempting" },
    { color: "#64748b", label: "Node: Offline"    },
    { color: "#f59e0b", label: "Ambulance"        },
    { color: "#ef4444", label: "Fire"             },
    { color: "#3b82f6", label: "Police"           },
];

export default function MapPage() {
    const [filterMode, setFilterMode]             = useState<FilterMode>("ALL");
    const [selectedVehicle, setSelectedVehicle]   = useState<MockVehicle | null>(null);
    const [showLegend, setShowLegend]             = useState(false);
    
    // Live Data State
    const [vehicles, setVehicles] = useState<MockVehicle[]>([]);
    const [nodes, setNodes] = useState<MockNode[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        async function fetchInitialData() {
            try {
                // Fetch vehicles (registry service port 8006)
                const vRes = await fetch('http://localhost:8006/api/v1/vehicles');
                const vData = await vRes.json();
                
                // Fetch nodes (health monitor service port 8002)
                const nRes = await fetch('http://localhost:8002/api/v1/nodes');
                const nData = await nRes.json();
                
                // Map vehicles
                const mappedVehicles: MockVehicle[] = vData.map((v: any) => ({
                    id: v.vehicle_id,
                    type: v.vehicle_type as VehicleType,
                    label: `${v.agency_name} ${v.vehicle_type}`,
                    lat: parseFloat(v.location_lat || "19.052"),
                    lon: parseFloat(v.location_lon || "72.877"),
                    speed: v.speed || 0,
                    heading: v.heading || 0,
                    siren: v.siren_active || false,
                    priority: v.priority_class,
                }));
                
                // Map nodes
                const mappedNodes: MockNode[] = nData.map((n: any) => ({
                    id: n.node_id,
                    name: n.intersection_name,
                    lat: parseFloat(n.location_lat || "0"),
                    lon: parseFloat(n.location_lon || "0"),
                    status: n.is_online ? "ACTIVE" : "OFFLINE", // Note: Preempting status will come via websocket later
                    preemptions_today: 0,
                    firmware: n.firmware_version || "Unknown",
                }));
                
                setVehicles(mappedVehicles);
                setNodes(mappedNodes);
            } catch (e) {
                console.error("Failed to load map data from APIs", e);
            } finally {
                setIsLoading(false);
            }
        }
        fetchInitialData();
    }, []);

    // ── KPI stats ──────────────────────────────────────────────────────────────────
    const activeVehicles    = vehicles.filter(v => v.siren).length;
    const preemptingNodes   = nodes.filter(n => n.status === "PREEMPTING").length;
    const offlineNodes      = nodes.filter(n => n.status === "OFFLINE").length;

    return (
        <div className="h-full flex flex-col gap-4">

            {/* ── Header ──────────────────────────────────────────────────── */}
            <header className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight text-white mb-1">Live Map</h1>
                    <p className="text-sm text-dark-text-muted">Real-time GPS tracking and signal preemption routes.</p>
                </div>

                {/* KPI badges */}
                <div className="flex items-center gap-2 flex-wrap">
                    <div className="glass-card px-3 py-1.5 rounded-lg flex items-center gap-2 text-sm">
                        <Activity className="w-4 h-4 text-brand-500" />
                        <span className="text-dark-text-muted">Active sirens:</span>
                        <span className="text-white font-semibold">{activeVehicles}</span>
                    </div>
                    <div className="glass-card px-3 py-1.5 rounded-lg flex items-center gap-2 text-sm">
                        <AlertTriangle className="w-4 h-4 text-accent-red" />
                        <span className="text-dark-text-muted">Preempting:</span>
                        <span className="text-accent-red font-semibold">{preemptingNodes}</span>
                    </div>
                    <div className="glass-card px-3 py-1.5 rounded-lg flex items-center gap-2 text-sm">
                        <Radio className="w-4 h-4 text-dark-text-muted" />
                        <span className="text-dark-text-muted">Offline nodes:</span>
                        <span className="text-white font-semibold">{offlineNodes}</span>
                    </div>
                </div>
            </header>

            {/* ── Toolbar ─────────────────────────────────────────────────── */}
            <div className="flex items-center gap-3 flex-wrap flex-shrink-0">
                {/* Filter toggles */}
                <div className="flex items-center glass-card rounded-lg p-1 gap-1">
                    {FILTERS.map(f => {
                        const Icon = f.icon;
                        return (
                            <button
                                key={f.value}
                                id={`map-filter-${f.value.toLowerCase()}`}
                                onClick={() => setFilterMode(f.value)}
                                className={cn(
                                    "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200",
                                    filterMode === f.value
                                        ? "bg-dark-border text-white shadow"
                                        : "text-dark-text-muted hover:text-white hover:bg-white/5"
                                )}
                            >
                                <Icon className="w-3.5 h-3.5" />
                                {f.label}
                            </button>
                        );
                    })}
                </div>

                {/* Legend toggle */}
                <div className="relative">
                    <button
                        id="map-legend-toggle"
                        onClick={() => setShowLegend(v => !v)}
                        className="glass-card px-3 py-1.5 rounded-lg text-sm text-dark-text-muted hover:text-white transition-colors flex items-center gap-1.5"
                    >
                        <Layers className="w-3.5 h-3.5" />
                        Legend
                    </button>
                    {showLegend && (
                        <div className="absolute top-9 left-0 z-50 glass-panel rounded-xl p-3 w-48 shadow-xl">
                            <p className="text-[10px] uppercase tracking-widest text-dark-text-muted font-semibold mb-2">
                                Map Legend
                            </p>
                            <ul className="space-y-1.5">
                                {LEGEND.map(l => (
                                    <li key={l.label} className="flex items-center gap-2 text-xs text-dark-text-main">
                                        <span
                                            className="w-3 h-3 rounded-full flex-shrink-0"
                                            style={{ background: l.color }}
                                        />
                                        {l.label}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>

                {/* Selected vehicle badge */}
                {selectedVehicle && (
                    <div className="ml-auto flex items-center gap-2 glass-card px-3 py-1.5 rounded-lg text-sm animate-slide-in">
                        <Car className="w-3.5 h-3.5 text-accent-amber" />
                        <span className="text-white font-mono">{selectedVehicle.id}</span>
                        <span className="text-dark-text-muted">selected</span>
                        <button
                            onClick={() => setSelectedVehicle(null)}
                            className="text-dark-text-muted hover:text-white ml-1 text-xs"
                        >
                            ✕
                        </button>
                    </div>
                )}
            </div>

            {/* ── Main content: Map + Feed ─────────────────────────────────── */}
            <div className="flex-1 flex gap-4 min-h-0">

                {/* Map panel */}
                <div className="flex-1 glass-panel rounded-xl overflow-hidden min-h-0 relative">
                    {isLoading ? (
                        <div className="absolute inset-0 z-10 flex items-center justify-center bg-dark-bg/50 backdrop-blur-sm">
                            <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                        </div>
                    ) : (
                        <LeafletMap
                            filterMode={filterMode}
                            initialVehicles={vehicles}
                            initialNodes={nodes}
                            onVehicleSelect={setSelectedVehicle}
                        />
                    )}
                </div>

                {/* Live feed panel */}
                <div className="w-72 flex-shrink-0 glass-panel rounded-xl p-4 overflow-hidden">
                    <LiveFeed />
                </div>
            </div>
        </div>
    );
}

