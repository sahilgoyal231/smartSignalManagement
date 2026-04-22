"use client";

import { useState, useMemo, useEffect } from "react";
import { Search, Activity, CheckCircle, XCircle, Clock, AlertTriangle, Timer, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";

interface PreemptionEvent {
    event_id: string;
    vehicle_id: string;
    node_id: string;
    triggered_at: string;
    cleared_at: string | null;
    eta_at_trigger_s: number;
    actual_arrival_s: number | null;
    approach_phase: number;
    sensor_confidence: number;
    trigger_method: string;
    outcome: "CLEARED" | "ABORTED" | "TIMEOUT" | "MANUAL";
    green_hold_duration_s: number | null;
}

const OUTCOME_CONFIG: Record<string, { icon: React.FC<{className?: string}>, label: string, badge: string }> = {
    CLEARED: { icon: CheckCircle, label: "Cleared",  badge: "bg-brand-500/15 text-brand-400" },
    ABORTED: { icon: XCircle,     label: "Aborted",  badge: "bg-accent-red/15 text-accent-red" },
    TIMEOUT: { icon: Clock,       label: "Timeout",  badge: "bg-accent-amber/15 text-accent-amber" },
    MANUAL:  { icon: AlertTriangle, label: "Manual", badge: "bg-dark-border/50 text-dark-text-muted" },
};

type OutcomeFilter = "ALL" | "CLEARED" | "ABORTED" | "TIMEOUT";

export default function EventsPage() {
    const [events, setEvents] = useState<PreemptionEvent[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchEvents() {
            try {
                const res = await fetch('http://localhost:8001/api/v1/events?limit=100');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                setEvents(data);
            } catch (e: any) {
                setError(e.message);
            } finally {
                setIsLoading(false);
            }
        }
        fetchEvents();
    }, []);

    const [search, setSearch] = useState("");
    const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("ALL");

    const filtered = useMemo(() => {
        return events.filter(e => {
            if (outcomeFilter !== "ALL" && e.outcome !== outcomeFilter) return false;
            const q = search.toLowerCase();
            return !q || e.vehicle_id.toLowerCase().includes(q) || e.node_id.toLowerCase().includes(q) || e.trigger_method.toLowerCase().includes(q);
        });
    }, [events, search, outcomeFilter]);

    // Stats
    const totalEvents = events.length;
    const clearedCount = events.filter(e => e.outcome === "CLEARED").length;
    const clearanceRate = totalEvents > 0 ? Math.round((clearedCount / totalEvents) * 100) : 0;
    const avgEta = events.length > 0
        ? (events.reduce((sum, e) => sum + e.eta_at_trigger_s, 0) / events.length).toFixed(1)
        : "0";
    const avgConfidence = events.length > 0
        ? (events.reduce((sum, e) => sum + e.sensor_confidence, 0) / events.length * 100).toFixed(0)
        : "0";

    return (
        <div className="space-y-5">
            <header>
                <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Preemption Event Log</h1>
                <p className="text-dark-text-muted">Full audit trail of every signal preemption triggered by emergency vehicles.</p>
            </header>

            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                    { label: "Total Events", value: totalEvents,         icon: Activity,   color: "text-white" },
                    { label: "Clearance Rate", value: `${clearanceRate}%`, icon: CheckCircle, color: "text-brand-500" },
                    { label: "Avg ETA",       value: `${avgEta}s`,        icon: Timer,      color: "text-accent-amber" },
                    { label: "Avg Confidence", value: `${avgConfidence}%`, icon: BarChart3,  color: "text-accent-blue" },
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

            {/* Main table */}
            <div className="glass-panel rounded-xl overflow-hidden">
                {/* Controls */}
                <div className="p-4 border-b border-dark-border flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                    <div className="flex items-center gap-1 glass-card rounded-lg p-1">
                        {(["ALL", "CLEARED", "ABORTED", "TIMEOUT"] as OutcomeFilter[]).map(val => (
                            <button
                                key={val}
                                onClick={() => setOutcomeFilter(val)}
                                className={cn(
                                    "px-3 py-1 rounded-md text-xs font-medium transition-all duration-200",
                                    outcomeFilter === val
                                        ? "bg-dark-border text-white shadow"
                                        : "text-dark-text-muted hover:text-white"
                                )}
                            >
                                {val === "ALL" ? "All" : val.charAt(0) + val.slice(1).toLowerCase()}
                            </button>
                        ))}
                    </div>

                    <div className="relative w-full sm:w-64">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dark-text-muted pointer-events-none" />
                        <input
                            type="text"
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder="Search by vehicle, node..."
                            className="w-full pl-9 pr-3 py-1.5 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                        />
                    </div>
                </div>

                {/* Table */}
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-dark-border/70">
                                {["Triggered", "Vehicle", "Node", "ETA", "Actual", "Phase", "Confidence", "Method", "Outcome"].map(h => (
                                    <th key={h} className="py-2.5 px-4 text-left text-[10px] uppercase tracking-wider text-dark-text-muted font-semibold">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-dark-text-muted text-sm animate-pulse">
                                        Loading preemption events...
                                    </td>
                                </tr>
                            ) : error ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-accent-red text-sm">
                                        Error: {error}
                                    </td>
                                </tr>
                            ) : filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-dark-text-muted text-sm">
                                        No events match your filters.
                                    </td>
                                </tr>
                            ) : (
                                filtered.map(evt => {
                                    const oc = OUTCOME_CONFIG[evt.outcome] || OUTCOME_CONFIG.CLEARED;
                                    const OcIcon = oc.icon;
                                    const triggered = new Date(evt.triggered_at);
                                    const etaAccuracy = evt.actual_arrival_s && evt.eta_at_trigger_s
                                        ? Math.abs(evt.actual_arrival_s - evt.eta_at_trigger_s).toFixed(1)
                                        : null;

                                    return (
                                        <tr
                                            key={evt.event_id}
                                            className="border-b border-dark-border/50 hover:bg-white/[0.02] transition-colors"
                                        >
                                            {/* Triggered */}
                                            <td className="py-3 px-4 whitespace-nowrap">
                                                <div className="text-xs text-white">{triggered.toLocaleDateString()}</div>
                                                <div className="text-[10px] text-dark-text-muted tabular-nums">{triggered.toLocaleTimeString()}</div>
                                            </td>
                                            {/* Vehicle */}
                                            <td className="py-3 px-4">
                                                <span className="font-mono text-xs text-white">{evt.vehicle_id}</span>
                                            </td>
                                            {/* Node */}
                                            <td className="py-3 px-4">
                                                <span className="font-mono text-xs text-dark-text-muted">{evt.node_id}</span>
                                            </td>
                                            {/* ETA */}
                                            <td className="py-3 px-4">
                                                <span className="text-xs text-accent-amber tabular-nums">{evt.eta_at_trigger_s.toFixed(1)}s</span>
                                            </td>
                                            {/* Actual */}
                                            <td className="py-3 px-4">
                                                {evt.actual_arrival_s ? (
                                                    <div>
                                                        <span className="text-xs text-white tabular-nums">{evt.actual_arrival_s.toFixed(1)}s</span>
                                                        {etaAccuracy && (
                                                            <span className={cn(
                                                                "ml-1 text-[10px] tabular-nums",
                                                                Number(etaAccuracy) < 5 ? "text-brand-400" : "text-accent-amber"
                                                            )}>
                                                                (±{etaAccuracy}s)
                                                            </span>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span className="text-xs text-dark-text-muted">—</span>
                                                )}
                                            </td>
                                            {/* Phase */}
                                            <td className="py-3 px-4 hidden md:table-cell">
                                                <span className="text-xs text-dark-text-muted">Phase {evt.approach_phase}</span>
                                            </td>
                                            {/* Confidence */}
                                            <td className="py-3 px-4 hidden lg:table-cell">
                                                <div className="flex items-center gap-2">
                                                    <div className="flex-1 h-1.5 bg-dark-border rounded-full overflow-hidden max-w-[60px]">
                                                        <div
                                                            className={cn(
                                                                "h-full rounded-full transition-all",
                                                                evt.sensor_confidence >= 0.9 ? "bg-brand-500" : evt.sensor_confidence >= 0.8 ? "bg-accent-amber" : "bg-accent-red"
                                                            )}
                                                            style={{ width: `${evt.sensor_confidence * 100}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-[10px] text-dark-text-muted tabular-nums">
                                                        {(evt.sensor_confidence * 100).toFixed(0)}%
                                                    </span>
                                                </div>
                                            </td>
                                            {/* Method */}
                                            <td className="py-3 px-4 hidden xl:table-cell">
                                                <span className="text-[10px] text-dark-text-muted font-mono">{evt.trigger_method}</span>
                                            </td>
                                            {/* Outcome */}
                                            <td className="py-3 px-4">
                                                <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full inline-flex items-center gap-1", oc.badge)}>
                                                    <OcIcon className="w-3 h-3" />
                                                    {oc.label}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Footer */}
                <div className="px-4 py-3 border-t border-dark-border/50 flex justify-between items-center">
                    <p className="text-xs text-dark-text-muted">
                        Showing <span className="text-white font-medium">{filtered.length}</span> of{" "}
                        <span className="text-white font-medium">{totalEvents}</span> events
                    </p>
                    <div className="flex items-center gap-1.5 text-xs text-dark-text-muted">
                        <Clock className="w-3 h-3" />
                        Last 7 days
                    </div>
                </div>
            </div>
        </div>
    );
}
