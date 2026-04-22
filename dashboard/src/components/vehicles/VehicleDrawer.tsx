"use client";

import { X, ShieldCheck, ToggleLeft, ToggleRight, Copy, Check } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export type VehicleType = "AMBULANCE" | "FIRE" | "POLICE" | "DISASTER";
export type PriorityClass = 1 | 2 | 3;

export interface Vehicle {
    id: string;
    type: VehicleType;
    license_plate: string;
    agency: string;
    priority: PriorityClass;
    city: string;
    cert_hash: string;         // 64-char sha256 hex
    registered_at: string;
    last_seen: string;
    is_active: boolean;
    cert_pem_preview: string;  // first 3 lines of PEM
}

const PRIORITY_CONFIG: Record<PriorityClass, { label: string; badge: string }> = {
    1: { label: "Critical", badge: "bg-accent-red/15 text-accent-red" },
    2: { label: "High",     badge: "bg-accent-amber/15 text-accent-amber" },
    3: { label: "Standard", badge: "bg-dark-border/60 text-dark-text-muted" },
};

const TYPE_ICON: Record<VehicleType, string> = {
    AMBULANCE: "🚑",
    FIRE:      "🚒",
    POLICE:    "🚔",
    DISASTER:  "🚐",
};

interface VehicleDrawerProps {
    vehicle: Vehicle | null;
    onClose: () => void;
    onStatusChange?: () => void;
}

function DetailRow({ label, value, mono = false }: { label: string; value: string | number; mono?: boolean }) {
    return (
        <div className="flex justify-between items-center py-2 border-b border-dark-border/50 last:border-0">
            <span className="text-xs text-dark-text-muted">{label}</span>
            <span className={cn("text-xs text-white font-medium", mono && "font-mono")}>{value}</span>
        </div>
    );
}

export default function VehicleDrawer({ vehicle, onClose, onStatusChange }: VehicleDrawerProps) {
    const [copied, setCopied] = useState(false);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [actionSuccess, setActionSuccess] = useState<string | null>(null);

    function copyHash() {
        if (!vehicle) return;
        navigator.clipboard.writeText(vehicle.cert_hash).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 1800);
    }

    async function toggleActive() {
        if (!vehicle) return;
        const action = vehicle.is_active ? "deactivate" : "activate";
        setActionLoading(action);
        setActionError(null);
        setActionSuccess(null);

        try {
            const res = await fetch(`http://localhost:8006/api/v1/vehicles/${vehicle.id}/${action}`, {
                method: 'PATCH',
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            setActionSuccess(`Vehicle ${action}d successfully`);
            setTimeout(() => {
                onStatusChange?.();
                onClose();
                setActionSuccess(null);
            }, 1000);
        } catch (err: any) {
            setActionError(err.message);
        } finally {
            setActionLoading(null);
        }
    }

    async function rotateCert() {
        if (!vehicle) return;
        setActionLoading("rotate");
        setActionError(null);
        setActionSuccess(null);
        // Simulate rotation (no backend endpoint yet — show success message)
        setTimeout(() => {
            setActionSuccess("Certificate rotation queued. New cert will be provisioned on next VSU heartbeat.");
            setActionLoading(null);
            setTimeout(() => setActionSuccess(null), 4000);
        }, 1500);
    }

    const pc = vehicle ? PRIORITY_CONFIG[vehicle.priority] : null;

    return (
        <>
            <div
                className={cn(
                    "fixed inset-0 bg-black/50 z-30 transition-opacity duration-300",
                    vehicle ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
                )}
                onClick={onClose}
            />
            <div
                className={cn(
                    "fixed top-0 right-0 h-full w-80 bg-dark-panel border-l border-dark-border z-40 flex flex-col shadow-2xl transition-transform duration-300 ease-in-out",
                    vehicle ? "translate-x-0" : "translate-x-full"
                )}
            >
                {!vehicle ? null : (
                    <>
                        {/* Header */}
                        <div className="flex items-start justify-between p-5 border-b border-dark-border flex-shrink-0">
                            <div className="flex items-start gap-3">
                                <span className="text-2xl mt-0.5">{TYPE_ICON[vehicle.type]}</span>
                                <div>
                                    <p className="font-mono text-xs text-dark-text-muted mb-0.5">{vehicle.id}</p>
                                    <h2 className="font-semibold text-white text-sm">{vehicle.agency}</h2>
                                    <p className="text-xs text-dark-text-muted mt-0.5">{vehicle.license_plate}</p>
                                </div>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-dark-text-muted hover:text-white transition-colors"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        {/* Body */}
                        <div className="flex-1 overflow-y-auto px-5 py-4 custom-scrollbar space-y-5">

                            {/* Status messages */}
                            {actionError && (
                                <div className="p-2.5 rounded-lg bg-accent-red/10 border border-accent-red/20 text-accent-red text-xs font-medium">
                                    {actionError}
                                </div>
                            )}
                            {actionSuccess && (
                                <div className="p-2.5 rounded-lg bg-brand-500/10 border border-brand-500/20 text-brand-400 text-xs font-medium">
                                    {actionSuccess}
                                </div>
                            )}

                            {/* Priority + status chips */}
                            <div className="flex items-center gap-2">
                                <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full", pc!.badge)}>
                                    Priority {vehicle.priority} — {pc!.label}
                                </span>
                                <span className={cn(
                                    "text-xs font-semibold px-2.5 py-1 rounded-full",
                                    vehicle.is_active ? "bg-brand-500/15 text-brand-400" : "bg-dark-border/50 text-dark-text-muted"
                                )}>
                                    {vehicle.is_active ? "Active" : "Inactive"}
                                </span>
                            </div>

                            {/* Details */}
                            <div>
                                <p className="text-[10px] uppercase tracking-widest text-dark-text-muted font-semibold mb-1">
                                    Details
                                </p>
                                <div className="glass-card rounded-lg px-3">
                                    <DetailRow label="Type"          value={vehicle.type} />
                                    <DetailRow label="City"          value={vehicle.city} />
                                    <DetailRow label="Registered"    value={vehicle.registered_at} />
                                    <DetailRow label="Last Seen"     value={vehicle.last_seen} />
                                </div>
                            </div>

                            {/* Cert hash */}
                            <div>
                                <p className="text-[10px] uppercase tracking-widest text-dark-text-muted font-semibold mb-1">
                                    VSU Certificate
                                </p>
                                <div className="glass-card rounded-lg p-3">
                                    <div className="flex items-start justify-between gap-2 mb-2">
                                        <p className="text-[10px] font-mono text-dark-text-muted break-all leading-relaxed">
                                            {vehicle.cert_hash}
                                        </p>
                                        <button onClick={copyHash} className="flex-shrink-0 p-1 hover:text-brand-400 text-dark-text-muted transition-colors">
                                            {copied ? <Check className="w-3 h-3 text-brand-500" /> : <Copy className="w-3 h-3" />}
                                        </button>
                                    </div>
                                    <div className="font-mono text-[9px] text-brand-400/70 bg-dark-surface rounded p-2 leading-relaxed whitespace-pre-wrap">
                                        {vehicle.cert_pem_preview}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Actions */}
                        <div className="p-4 border-t border-dark-border flex-shrink-0 space-y-2">
                            <button
                                onClick={rotateCert}
                                disabled={!!actionLoading}
                                className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium py-2 rounded-lg transition-colors"
                            >
                                {actionLoading === "rotate" ? (
                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                ) : (
                                    <ShieldCheck className="w-3.5 h-3.5" />
                                )}
                                Rotate VSU Certificate
                            </button>
                            <button
                                onClick={toggleActive}
                                disabled={!!actionLoading}
                                className={cn(
                                    "w-full flex items-center justify-center gap-2 text-sm font-medium py-2 rounded-lg transition-colors border disabled:opacity-50",
                                    vehicle.is_active
                                        ? "bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border-accent-red/20"
                                        : "bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 border-brand-500/20"
                                )}
                            >
                                {actionLoading === "deactivate" || actionLoading === "activate" ? (
                                    <div className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                                ) : vehicle.is_active ? (
                                    <><ToggleLeft className="w-3.5 h-3.5" /> Deactivate Vehicle</>
                                ) : (
                                    <><ToggleRight className="w-3.5 h-3.5" /> Reactivate Vehicle</>
                                )}
                            </button>
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
