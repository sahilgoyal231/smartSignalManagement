"use client";

import { useState, useMemo, useEffect } from "react";
import { Search, Plus, Car, ShieldCheck, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import VehicleDrawer, { Vehicle, VehicleType, PriorityClass } from "@/components/vehicles/VehicleDrawer";

// ── Live Data Fetching ───────────────────────────────────────────────────────

// ── Live Data Fetching ───────────────────────────────────────────────────────
const TYPE_ICON: Record<VehicleType, string> = {
    AMBULANCE: "🚑",
    FIRE:      "🚒",
    POLICE:    "🚔",
    DISASTER:  "🚐",
};

const PRIORITY_BADGE: Record<PriorityClass, string> = {
    1: "bg-accent-red/15 text-accent-red",
    2: "bg-accent-amber/15 text-accent-amber",
    3: "bg-dark-border/50 text-dark-text-muted",
};
const PRIORITY_LABELS: Record<PriorityClass, string> = {
    1: "Critical", 2: "High", 3: "Standard",
};

type TypeFilter = "ALL" | VehicleType;

export default function VehiclesPage() {
    // API Data state
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchVehicles() {
            try {
                // Fetch vehicles (registry service is on port 8006, not 8001)
                const res = await fetch('http://localhost:8006/api/v1/vehicles');
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                const data = await res.json();
                
                // Map backend model to frontend model
                const mapped: Vehicle[] = data.map((v: any) => ({
                    id: v.vehicle_id,
                    type: v.vehicle_type,
                    license_plate: v.license_plate,
                    agency: v.agency_name,
                    priority: v.priority_class as PriorityClass,
                    city: v.city,
                    cert_hash: v.vsu_cert_hash,
                    registered_at: new Date(v.created_at).toLocaleDateString(),
                    last_seen: v.last_seen ? new Date(v.last_seen).toLocaleTimeString() : 'Never',
                    is_active: v.is_active,
                    cert_pem_preview: v.vsu_cert_pem,
                }));
                
                setVehicles(mapped);
            } catch (e: any) {
                console.error("Failed to fetch vehicles:", e);
                setError(e.message);
            } finally {
                setIsLoading(false);
            }
        }
        fetchVehicles();
    }, []);

    // Derived state
    const [search, setSearch]           = useState("");
    const [typeFilter, setTypeFilter]   = useState<TypeFilter>("ALL");
    const [activeOnly, setActiveOnly]   = useState(false);
    const [selectedVehicle, setSelectedVehicle] = useState<Vehicle | null>(null);

    const filtered = useMemo(() => {
        return vehicles.filter(v => {
            if (typeFilter !== "ALL" && v.type !== typeFilter) return false;
            if (activeOnly && !v.is_active) return false;
            const q = search.toLowerCase();
            return (
                !q ||
                v.id.toLowerCase().includes(q) ||
                v.agency.toLowerCase().includes(q) ||
                v.license_plate.toLowerCase().includes(q) ||
                v.city.toLowerCase().includes(q)
            );
        });
    }, [search, typeFilter, activeOnly, vehicles]);

    const TYPE_TABS: { label: string; value: TypeFilter }[] = [
        { label: "All",       value: "ALL"       },
        { label: "🚑",        value: "AMBULANCE" },
        { label: "🚒",        value: "FIRE"      },
        { label: "🚔",        value: "POLICE"    },
        { label: "🚐",        value: "DISASTER"  },
    ];

    return (
        <div className="space-y-5">
            {/* Header */}
            <header className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Fleet Registry</h1>
                    <p className="text-dark-text-muted">Provision and deactivate secure VSU certificates for emergency responders.</p>
                </div>
                <button
                    id="register-vehicle-btn"
                    className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors shadow-sm"
                >
                    <Plus className="w-4 h-4" />
                    Register Vehicle
                </button>
            </header>

            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                    { label: "Total",    value: vehicles.length,                                 icon: Users,       color: "text-white" },
                    { label: "Active",   value: vehicles.filter(v => v.is_active).length,       icon: ShieldCheck, color: "text-brand-500" },
                    { label: "Priority 1", value: vehicles.filter(v => v.priority === 1).length, icon: Car,        color: "text-accent-red" },
                    { label: "Inactive", value: vehicles.filter(v => !v.is_active).length,      icon: Car,         color: "text-dark-text-muted" },
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

            {/* Table panel */}
            <div className="glass-panel rounded-xl overflow-hidden">
                {/* Control bar */}
                <div className="p-4 border-b border-dark-border flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between flex-wrap">
                    {/* Type filter */}
                    <div className="flex items-center gap-1 glass-card rounded-lg p-1">
                        {TYPE_TABS.map(t => (
                            <button
                                key={t.value}
                                id={`vehicle-filter-${t.value.toLowerCase()}`}
                                onClick={() => setTypeFilter(t.value)}
                                className={cn(
                                    "px-3 py-1 rounded-md text-xs font-medium transition-all duration-200",
                                    typeFilter === t.value
                                        ? "bg-dark-border text-white shadow"
                                        : "text-dark-text-muted hover:text-white"
                                )}
                            >
                                {t.label}
                            </button>
                        ))}
                    </div>

                    <div className="flex items-center gap-3 flex-wrap">
                        {/* Active only toggle */}
                        <label className="flex items-center gap-2 cursor-pointer select-none">
                            <div
                                onClick={() => setActiveOnly(v => !v)}
                                className={cn(
                                    "w-8 h-4 rounded-full transition-colors relative cursor-pointer",
                                    activeOnly ? "bg-brand-500" : "bg-dark-border"
                                )}
                            >
                                <span className={cn(
                                    "absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform",
                                    activeOnly && "translate-x-4"
                                )} />
                            </div>
                            <span className="text-xs text-dark-text-muted">Active only</span>
                        </label>

                        {/* Search */}
                        <div className="relative w-full sm:w-56">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dark-text-muted pointer-events-none" />
                            <input
                                id="vehicle-search"
                                type="text"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                placeholder="Search vehicles…"
                                className="w-full pl-9 pr-3 py-1.5 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
                            />
                        </div>
                    </div>
                </div>

                {/* Table */}
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-dark-border/70">
                                {["Vehicle ID", "Agency", "License", "Priority", "City", "Cert Hash", "Registered", "Status", ""].map(h => (
                                    <th key={h} className="py-2.5 px-4 text-left text-[10px] uppercase tracking-wider text-dark-text-muted font-semibold">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="py-16 text-center text-dark-text-muted text-sm">
                                        No vehicles match your filters.
                                    </td>
                                </tr>
                            ) : (
                                filtered.map(v => (
                                    <tr
                                        key={v.id}
                                        onClick={() => setSelectedVehicle(prev => prev?.id === v.id ? null : v)}
                                        className={cn(
                                            "border-b border-dark-border/50 cursor-pointer transition-colors",
                                            selectedVehicle?.id === v.id ? "bg-brand-500/5" : "hover:bg-white/[0.02]"
                                        )}
                                    >
                                        {/* ID + type icon */}
                                        <td className="py-3 px-4 whitespace-nowrap">
                                            <div className="flex items-center gap-1.5">
                                                <span>{TYPE_ICON[v.type]}</span>
                                                <span className="font-mono text-xs text-white">{v.id}</span>
                                            </div>
                                        </td>
                                        {/* Agency */}
                                        <td className="py-3 px-4">
                                            <span className="text-sm text-dark-text-main line-clamp-1">{v.agency}</span>
                                        </td>
                                        {/* License */}
                                        <td className="py-3 px-4 hidden sm:table-cell">
                                            <span className="font-mono text-xs text-dark-text-muted">{v.license_plate}</span>
                                        </td>
                                        {/* Priority */}
                                        <td className="py-3 px-4 hidden md:table-cell">
                                            <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full", PRIORITY_BADGE[v.priority])}>
                                                P{v.priority} · {PRIORITY_LABELS[v.priority]}
                                            </span>
                                        </td>
                                        {/* City */}
                                        <td className="py-3 px-4 hidden md:table-cell">
                                            <span className="text-xs text-dark-text-muted">{v.city}</span>
                                        </td>
                                        {/* Cert hash (truncated) */}
                                        <td className="py-3 px-4 hidden lg:table-cell">
                                            <span className="font-mono text-[10px] text-dark-text-muted">{v.cert_hash.slice(0, 12)}…</span>
                                        </td>
                                        {/* Registered */}
                                        <td className="py-3 px-4 hidden xl:table-cell">
                                            <span className="text-xs text-dark-text-muted">{v.registered_at}</span>
                                        </td>
                                        {/* Active badge */}
                                        <td className="py-3 px-4 hidden sm:table-cell">
                                            <span className={cn(
                                                "text-[11px] font-semibold px-2 py-0.5 rounded-full",
                                                v.is_active ? "bg-brand-500/15 text-brand-400" : "bg-dark-border/50 text-dark-text-muted"
                                            )}>
                                                {v.is_active ? "Active" : "Inactive"}
                                            </span>
                                        </td>
                                        {/* Chevron */}
                                        <td className="py-3 px-4 text-right">
                                            <svg
                                                className={cn(
                                                    "w-4 h-4 text-dark-text-muted transition-transform duration-200 inline-block",
                                                    selectedVehicle?.id === v.id && "rotate-90 text-brand-400"
                                                )}
                                                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                                            >
                                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                                            </svg>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Footer */}
                <div className="px-4 py-3 border-t border-dark-border/50 flex justify-between items-center">
                    <p className="text-xs text-dark-text-muted">
                        Showing <span className="text-white font-medium">{filtered.length}</span> of{" "}
                        <span className="text-white font-medium">{vehicles.length}</span> vehicles
                    </p>
                    <div className="flex items-center gap-1.5 text-xs text-dark-text-muted">
                        <ShieldCheck className="w-3 h-3" />
                        ECDSA-P256 · TLS 1.3
                    </div>
                </div>
            </div>

            {/* Drawer */}
            <VehicleDrawer vehicle={selectedVehicle} onClose={() => setSelectedVehicle(null)} />
        </div>
    );
}
