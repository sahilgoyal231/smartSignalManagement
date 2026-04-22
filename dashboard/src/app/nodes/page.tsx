"use client";

import { useState, useMemo, useEffect } from "react";
import { Search, Plus, Activity, WifiOff, Zap, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import NodeRow, { EdgeNode } from "@/components/nodes/NodeRow";
import NodeDrawer from "@/components/nodes/NodeDrawer";

// ── Live Data Fetching ───────────────────────────────────────────────────────

type StatusFilter = "ALL" | "ACTIVE" | "PREEMPTING" | "OFFLINE";

const STATUS_TABS: { label: string; value: StatusFilter }[] = [
    { label: "All", value: "ALL" },
    { label: "Active", value: "ACTIVE" },
    { label: "Preempting", value: "PREEMPTING" },
    { label: "Offline", value: "OFFLINE" },
];

// ── Page ────────────────────────────────────────────────────────────────────

export default function NodesPage() {
    const [nodes, setNodes] = useState<EdgeNode[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchNodes() {
            try {
                // Fetch from Health Monitor service (port 8002)
                const res = await fetch('http://localhost:8002/api/v1/nodes');
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                const data = await res.json();
                
                // Map backend to UI model
                const mapped: EdgeNode[] = data.map((n: any) => ({
                    id: n.node_id,
                    name: n.intersection_name,
                    city: n.city,
                    status: n.is_online ? "ACTIVE" : "OFFLINE", // We'll refine PREEMPTING via websocket later
                    firmware: n.firmware_version || "Unknown",
                    controller_type: "PLC_NTCIP", // Stubbed
                    preemptions_today: 0,         // Stubbed
                    preemptions_week: [0,0,0,0,0,0,0],
                    last_heartbeat: n.last_heartbeat ? new Date(n.last_heartbeat).toLocaleTimeString() : "Never",
                    lat: parseFloat(n.location_lat || "0"),
                    lon: parseFloat(n.location_lon || "0"),
                    installed_at: "Dec 2025",
                    max_green_hold_s: 60,
                    preempt_threshold_s: 45
                }));
                
                setNodes(mapped);
            } catch (e: any) {
                console.error("Failed to fetch nodes:", e);
                setError(e.message);
            } finally {
                setIsLoading(false);
            }
        }
        fetchNodes();
    }, []);

    const [search, setSearch]         = useState("");
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
    const [selectedNode, setSelectedNode] = useState<EdgeNode | null>(null);

    // Derived stats
    const total      = nodes.length;
    const online     = nodes.filter(n => n.status !== "OFFLINE").length;
    const preempting = nodes.filter(n => n.status === "PREEMPTING").length;
    const offline    = nodes.filter(n => n.status === "OFFLINE").length;

    const filtered = useMemo(() => {
        return nodes.filter(n => {
            const matchStatus = statusFilter === "ALL" || n.status === statusFilter;
            const q = search.toLowerCase();
            const matchSearch =
                !q ||
                n.id.toLowerCase().includes(q) ||
                n.name.toLowerCase().includes(q) ||
                n.city.toLowerCase().includes(q);
            return matchStatus && matchSearch;
        });
    }, [search, statusFilter, nodes]);

    return (
        <div className="space-y-5">
            {/* Header */}
            <header className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Edge Nodes</h1>
                    <p className="text-dark-text-muted">Manage intersection hardware, monitor uptime, and trigger OTA updates.</p>
                </div>
                <button
                    id="add-node-btn"
                    className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors shadow-sm"
                >
                    <Plus className="w-4 h-4" />
                    Add Node
                </button>
            </header>

            {/* Summary strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                    { label: "Total Nodes",  value: total,      icon: Server,   color: "text-white" },
                    { label: "Online",       value: online,     icon: Activity, color: "text-brand-500" },
                    { label: "Preempting",   value: preempting, icon: Zap,      color: "text-accent-red" },
                    { label: "Offline",      value: offline,    icon: WifiOff,  color: "text-dark-text-muted" },
                ].map(s => {
                    const Icon = s.icon;
                    return (
                        <div key={s.label} className="glass-card rounded-xl px-4 py-3 flex items-center gap-3">
                            <Icon className={cn("w-5 h-5 flex-shrink-0", s.color)} />
                            <div>
                                <p className={cn("text-xl font-bold tabular-nums", s.color)}>{s.value}</p>
                                <p className="text-[10px] text-dark-text-muted uppercase tracking-widest font-medium">{s.label}</p>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Main table panel */}
            <div className="glass-panel rounded-xl overflow-hidden">
                {/* Control bar */}
                <div className="p-4 border-b border-dark-border flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                    {/* Status tabs */}
                    <div className="flex items-center gap-1 glass-card rounded-lg p-1">
                        {STATUS_TABS.map(t => (
                            <button
                                key={t.value}
                                id={`node-filter-${t.value.toLowerCase()}`}
                                onClick={() => setStatusFilter(t.value)}
                                className={cn(
                                    "px-3 py-1 rounded-md text-xs font-medium transition-all duration-200",
                                    statusFilter === t.value
                                        ? "bg-dark-border text-white shadow"
                                        : "text-dark-text-muted hover:text-white"
                                )}
                            >
                                {t.label}
                            </button>
                        ))}
                    </div>

                    {/* Search */}
                    <div className="relative w-full sm:w-64">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dark-text-muted pointer-events-none" />
                        <input
                            id="node-search"
                            type="text"
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder="Search nodes…"
                            className="w-full pl-9 pr-3 py-1.5 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                        />
                    </div>
                </div>

                {/* Table */}
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-dark-border/70">
                                {["Node ID", "Intersection", "City", "Status", "Controller", "Today", "Firmware", "Heartbeat", ""].map(h => (
                                    <th key={h} className="py-2.5 px-4 text-left text-[10px] uppercase tracking-wider text-dark-text-muted font-semibold first:pl-4 last:hidden xl:last:table-cell">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-dark-text-muted text-sm animate-pulse">
                                        Loading edge nodes...
                                    </td>
                                </tr>
                            ) : error ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-accent-red text-sm font-semibold bg-accent-red/5">
                                        Error connecting to cloud API: {error}
                                    </td>
                                </tr>
                            ) : filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-dark-text-muted text-sm">
                                        No nodes match your search.
                                    </td>
                                </tr>
                            ) : (
                                filtered.map(node => (
                                    <NodeRow
                                        key={node.id}
                                        node={node}
                                        selected={selectedNode?.id === node.id}
                                        onSelect={n => setSelectedNode(prev => prev?.id === n.id ? null : n)}
                                    />
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Footer */}
                <div className="px-4 py-3 border-t border-dark-border/50 flex justify-between items-center">
                    <p className="text-xs text-dark-text-muted">
                        Showing <span className="text-white font-medium">{filtered.length}</span> of{" "}
                        <span className="text-white font-medium">{total}</span> nodes
                    </p>
                    <div className="flex items-center gap-1.5 text-xs text-brand-400">
                        <Activity className="w-3 h-3 animate-pulse" />
                        Live sync active
                    </div>
                </div>
            </div>

            {/* Drawer */}
            <NodeDrawer node={selectedNode} onClose={() => setSelectedNode(null)} />
        </div>
    );
}
