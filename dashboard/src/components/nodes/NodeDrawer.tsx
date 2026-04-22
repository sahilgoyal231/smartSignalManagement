"use client";

import { X, Wifi, WifiOff, Zap, RefreshCw, GitBranch } from "lucide-react";
import { EdgeNode, NodeStatus } from "./NodeRow";
import { cn } from "@/lib/utils";

const STATUS_COLOR: Record<NodeStatus, string> = {
    ACTIVE:     "text-brand-500",
    PREEMPTING: "text-accent-red",
    OFFLINE:    "text-dark-text-muted",
};

interface NodeDrawerProps {
    node: EdgeNode | null;
    onClose: () => void;
}

function MiniBarChart({ data }: { data: number[] }) {
    const max = Math.max(...data, 1);
    const days = ["Today", "D-1", "D-2", "D-3", "D-4", "D-5", "D-6"];
    return (
        <div className="mt-2">
            <div className="flex items-end gap-1.5 h-10">
                {[...data].reverse().map((v, i) => (
                    <div key={i} className="flex-1 flex flex-col items-center justify-end gap-1">
                        <div
                            className={cn(
                                "w-full rounded-sm transition-all",
                                i === data.length - 1 ? "bg-accent-amber" : "bg-brand-500/60"
                            )}
                            style={{ height: `${(v / max) * 100}%`, minHeight: v > 0 ? "4px" : "2px" }}
                        />
                    </div>
                ))}
            </div>
            <div className="flex gap-1.5 mt-1">
                {days.map((d, i) => (
                    <div key={i} className="flex-1 text-center text-[9px] text-dark-text-muted">{d}</div>
                ))}
            </div>
        </div>
    );
}

function DetailRow({ label, value, mono = false }: { label: string; value: string | number; mono?: boolean }) {
    return (
        <div className="flex justify-between items-center py-2 border-b border-dark-border/50 last:border-0">
            <span className="text-xs text-dark-text-muted">{label}</span>
            <span className={cn("text-xs text-white font-medium", mono && "font-mono")}>{value}</span>
        </div>
    );
}

export default function NodeDrawer({ node, onClose }: NodeDrawerProps) {
    return (
        <>
            {/* Backdrop */}
            <div
                className={cn(
                    "fixed inset-0 bg-black/50 z-30 transition-opacity duration-300",
                    node ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
                )}
                onClick={onClose}
            />

            {/* Drawer */}
            <div
                className={cn(
                    "fixed top-0 right-0 h-full w-80 bg-dark-panel border-l border-dark-border z-40 flex flex-col shadow-2xl transition-transform duration-300 ease-in-out",
                    node ? "translate-x-0" : "translate-x-full"
                )}
            >
                {!node ? null : (
                    <>
                        {/* Header */}
                        <div className="flex items-start justify-between p-5 border-b border-dark-border flex-shrink-0">
                            <div>
                                <p className="font-mono text-xs text-dark-text-muted mb-0.5">{node.id}</p>
                                <h2 className="font-semibold text-white text-sm leading-snug">{node.name}</h2>
                                <p className={cn("text-xs font-semibold mt-1", STATUS_COLOR[node.status])}>
                                    ● {node.status}
                                </p>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-1.5 rounded-lg hover:bg-white/5 text-dark-text-muted hover:text-white transition-colors mt-0.5"
                                aria-label="Close drawer"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        {/* Body */}
                        <div className="flex-1 overflow-y-auto px-5 py-4 custom-scrollbar space-y-5">

                            {/* Preemption history */}
                            <div>
                                <p className="text-[10px] uppercase tracking-widest text-dark-text-muted font-semibold mb-1">
                                    Preemptions — Last 7 Days
                                </p>
                                <MiniBarChart data={node.preemptions_week} />
                                <p className="text-xs text-dark-text-muted mt-1 text-right">
                                    Total today: <span className="text-accent-amber font-semibold">{node.preemptions_today}</span>
                                </p>
                            </div>

                            {/* Node specs */}
                            <div>
                                <p className="text-[10px] uppercase tracking-widest text-dark-text-muted font-semibold mb-1">
                                    Hardware
                                </p>
                                <div className="glass-card rounded-lg px-3">
                                    <DetailRow label="Controller" value={node.controller_type} mono />
                                    <DetailRow label="Firmware" value={`v${node.firmware}`} mono />
                                    <DetailRow label="Installed" value={node.installed_at} />
                                    <DetailRow label="City" value={node.city} />
                                    <DetailRow label="Last Heartbeat" value={node.last_heartbeat} />
                                </div>
                            </div>

                            {/* Signal config */}
                            <div>
                                <p className="text-[10px] uppercase tracking-widest text-dark-text-muted font-semibold mb-1">
                                    Signal Config
                                </p>
                                <div className="glass-card rounded-lg px-3">
                                    <DetailRow label="Preempt Threshold" value={`${node.preempt_threshold_s}s`} />
                                    <DetailRow label="Max Green Hold" value={`${node.max_green_hold_s}s`} />
                                    <DetailRow label="Location" value={`${node.lat.toFixed(4)}, ${node.lon.toFixed(4)}`} mono />
                                </div>
                            </div>
                        </div>

                        {/* Actions */}
                        <div className="p-4 border-t border-dark-border flex-shrink-0 space-y-2">
                            <button className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium py-2 rounded-lg transition-colors">
                                <RefreshCw className="w-3.5 h-3.5" />
                                Trigger OTA Update
                            </button>
                            <div className="flex gap-2">
                                <button className="flex-1 flex items-center justify-center gap-1.5 glass-card hover:bg-white/5 text-dark-text-muted hover:text-white text-xs py-2 rounded-lg transition-colors">
                                    <GitBranch className="w-3 h-3" />
                                    View Logs
                                </button>
                                <button className="flex-1 flex items-center justify-center gap-1.5 bg-accent-red/10 hover:bg-accent-red/20 text-accent-red text-xs py-2 rounded-lg transition-colors border border-accent-red/20">
                                    {node.status === "OFFLINE"
                                        ? <><Wifi className="w-3 h-3" /> Reactivate</>
                                        : <><WifiOff className="w-3 h-3" /> Deactivate</>
                                    }
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
