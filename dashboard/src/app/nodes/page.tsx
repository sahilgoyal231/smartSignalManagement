"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Search, Plus, Activity, WifiOff, Zap, Server, X } from "lucide-react";
import { cn } from "@/lib/utils";
import NodeRow, { EdgeNode } from "@/components/nodes/NodeRow";
import NodeDrawer from "@/components/nodes/NodeDrawer";

type StatusFilter = "ALL" | "ACTIVE" | "PREEMPTING" | "OFFLINE";

const STATUS_TABS: { label: string; value: StatusFilter }[] = [
    { label: "All", value: "ALL" },
    { label: "Active", value: "ACTIVE" },
    { label: "Preempting", value: "PREEMPTING" },
    { label: "Offline", value: "OFFLINE" },
];

// ── Add Node Modal ──────────────────────────────────────────────────────────

function AddNodeModal({ open, onClose, onSuccess }: {
    open: boolean;
    onClose: () => void;
    onSuccess: () => void;
}) {
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [form, setForm] = useState({
        node_id: "",
        intersection_name: "",
        city: "Mumbai",
        location_lat: "",
        location_lon: "",
        firmware_version: "2.3.1",
        controller_type: "PLC_NTCIP",
    });

    const updateField = (key: string, value: string) =>
        setForm(prev => ({ ...prev, [key]: value }));

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setSubmitting(true);
        setError(null);

        try {
            const res = await fetch('http://localhost:8002/api/v1/nodes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...form,
                    location_lat: parseFloat(form.location_lat),
                    location_lon: parseFloat(form.location_lon),
                    is_online: true,
                }),
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || `HTTP ${res.status}`);
            }

            onSuccess();
            onClose();
            setForm(prev => ({ ...prev, node_id: "", intersection_name: "", location_lat: "", location_lon: "" }));
        } catch (err: any) {
            setError(err.message);
        } finally {
            setSubmitting(false);
        }
    }

    if (!open) return null;

    return (
        <>
            <div className="fixed inset-0 bg-black/60 z-50" onClick={onClose} />
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                <div className="glass-panel rounded-2xl w-full max-w-lg shadow-2xl animate-slide-in" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-between p-5 border-b border-dark-border">
                        <div>
                            <h2 className="text-lg font-semibold text-white">Register New Edge Node</h2>
                            <p className="text-xs text-dark-text-muted">Deploy a new intersection controller to the network</p>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg text-dark-text-muted hover:text-white transition-colors">
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    <form onSubmit={handleSubmit} className="p-5 space-y-4">
                        {error && (
                            <div className="p-3 rounded-lg bg-accent-red/10 border border-accent-red/20 text-accent-red text-xs font-medium">
                                {error}
                            </div>
                        )}

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-xs text-dark-text-muted font-medium mb-1 block">Node ID *</label>
                                <input
                                    required
                                    value={form.node_id}
                                    onChange={e => updateField("node_id", e.target.value)}
                                    placeholder="NODE-MUM-009"
                                    className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                                />
                            </div>
                            <div>
                                <label className="text-xs text-dark-text-muted font-medium mb-1 block">City</label>
                                <input
                                    value={form.city}
                                    onChange={e => updateField("city", e.target.value)}
                                    className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="text-xs text-dark-text-muted font-medium mb-1 block">Intersection Name *</label>
                            <input
                                required
                                value={form.intersection_name}
                                onChange={e => updateField("intersection_name", e.target.value)}
                                placeholder="Worli Sea Link Entry"
                                className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-xs text-dark-text-muted font-medium mb-1 block">Latitude *</label>
                                <input
                                    required
                                    type="number"
                                    step="0.0001"
                                    value={form.location_lat}
                                    onChange={e => updateField("location_lat", e.target.value)}
                                    placeholder="19.0330"
                                    className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                                />
                            </div>
                            <div>
                                <label className="text-xs text-dark-text-muted font-medium mb-1 block">Longitude *</label>
                                <input
                                    required
                                    type="number"
                                    step="0.0001"
                                    value={form.location_lon}
                                    onChange={e => updateField("location_lon", e.target.value)}
                                    placeholder="72.8410"
                                    className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="text-xs text-dark-text-muted font-medium mb-1 block">Controller</label>
                                <select
                                    value={form.controller_type}
                                    onChange={e => updateField("controller_type", e.target.value)}
                                    className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
                                >
                                    <option value="PLC_NTCIP">PLC_NTCIP</option>
                                    <option value="SCOOT">SCOOT</option>
                                    <option value="RELAY">RELAY</option>
                                    <option value="ECONOLITE">ECONOLITE</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-xs text-dark-text-muted font-medium mb-1 block">Firmware</label>
                                <input
                                    value={form.firmware_version}
                                    onChange={e => updateField("firmware_version", e.target.value)}
                                    className="w-full bg-dark-surface border border-dark-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
                                />
                            </div>
                        </div>

                        <div className="pt-2 flex gap-3">
                            <button
                                type="button"
                                onClick={onClose}
                                className="flex-1 px-4 py-2.5 glass-card rounded-lg text-sm text-dark-text-muted hover:text-white transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={submitting}
                                className="flex-1 px-4 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                            >
                                {submitting ? (
                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                ) : (
                                    <>
                                        <Server className="w-4 h-4" />
                                        Deploy Node
                                    </>
                                )}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </>
    );
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function NodesPage() {
    const [nodes, setNodes] = useState<EdgeNode[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showAddModal, setShowAddModal] = useState(false);

    const fetchNodes = useCallback(async () => {
        try {
            const res = await fetch('http://localhost:8002/api/v1/nodes');
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            const data = await res.json();
            
            const mapped: EdgeNode[] = data.map((n: any) => ({
                id: n.node_id,
                name: n.intersection_name,
                city: n.city,
                status: n.is_online ? "ACTIVE" : "OFFLINE",
                firmware: n.firmware_version || "Unknown",
                controller_type: n.controller_type || "PLC_NTCIP",
                preemptions_today: 0,
                preemptions_week: [0, 0, 0, 0, 0, 0, 0],
                last_heartbeat: n.last_heartbeat ? new Date(n.last_heartbeat).toLocaleTimeString() : "Never",
                lat: parseFloat(n.location_lat || "0"),
                lon: parseFloat(n.location_lon || "0"),
                installed_at: n.installed_at ? new Date(n.installed_at).toLocaleDateString() : "N/A",
                max_green_hold_s: n.max_green_hold_s || 60,
                preempt_threshold_s: n.preempt_threshold_s || 45,
            }));
            
            setNodes(mapped);
            setError(null);
        } catch (e: any) {
            console.error("Failed to fetch nodes:", e);
            setError(e.message);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchNodes();
    }, [fetchNodes]);

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
                    onClick={() => setShowAddModal(true)}
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

            {/* Add Node Modal */}
            <AddNodeModal
                open={showAddModal}
                onClose={() => setShowAddModal(false)}
                onSuccess={fetchNodes}
            />
        </div>
    );
}
