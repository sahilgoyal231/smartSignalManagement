"use client";

import { cn } from "@/lib/utils";

export type NodeStatus = "ACTIVE" | "PREEMPTING" | "OFFLINE";
export type ControllerType = "PLC_NTCIP" | "RELAY" | "SCOOT" | "ECONOLITE";

export interface EdgeNode {
    id: string;
    name: string;
    city: string;
    status: NodeStatus;
    firmware: string;
    preemptions_today: number;
    preemptions_week: number[];   // 7-day history newest-first
    last_heartbeat: string;       // e.g. "2 min ago"
    controller_type: ControllerType;
    lat: number;
    lon: number;
    installed_at: string;
    max_green_hold_s: number;
    preempt_threshold_s: number;
}

const STATUS_CONFIG: Record<NodeStatus, { dot: string; label: string; badge: string }> = {
    ACTIVE:     { dot: "bg-brand-500",   label: "Active",     badge: "bg-brand-500/15 text-brand-400" },
    PREEMPTING: { dot: "bg-accent-red animate-pulse", label: "Preempting", badge: "bg-accent-red/15 text-accent-red" },
    OFFLINE:    { dot: "bg-dark-border", label: "Offline",    badge: "bg-dark-border/50 text-dark-text-muted" },
};

interface NodeRowProps {
    node: EdgeNode;
    selected: boolean;
    onSelect: (node: EdgeNode) => void;
}

export default function NodeRow({ node, selected, onSelect }: NodeRowProps) {
    const sc = STATUS_CONFIG[node.status];
    return (
        <tr
            onClick={() => onSelect(node)}
            className={cn(
                "border-b border-dark-border/50 cursor-pointer transition-colors",
                selected
                    ? "bg-brand-500/5"
                    : "hover:bg-white/[0.02]"
            )}
        >
            {/* Status + ID */}
            <td className="py-3 px-4 whitespace-nowrap">
                <div className="flex items-center gap-2.5">
                    <div className={cn("w-2 h-2 rounded-full flex-shrink-0", sc.dot)} />
                    <span className="font-mono text-xs text-white">{node.id}</span>
                </div>
            </td>

            {/* Intersection name */}
            <td className="py-3 px-4">
                <span className="text-sm text-dark-text-main line-clamp-1">{node.name}</span>
            </td>

            {/* City */}
            <td className="py-3 px-4 hidden sm:table-cell">
                <span className="text-sm text-dark-text-muted">{node.city}</span>
            </td>

            {/* Status badge */}
            <td className="py-3 px-4 hidden md:table-cell">
                <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full", sc.badge)}>
                    {sc.label}
                </span>
            </td>

            {/* Controller */}
            <td className="py-3 px-4 hidden lg:table-cell">
                <span className="text-xs text-dark-text-muted font-mono">{node.controller_type}</span>
            </td>

            {/* Preemptions today */}
            <td className="py-3 px-4 text-center hidden md:table-cell">
                <span className={cn(
                    "text-sm font-semibold tabular-nums",
                    node.preemptions_today > 0 ? "text-accent-amber" : "text-dark-text-muted"
                )}>
                    {node.preemptions_today}
                </span>
            </td>

            {/* Firmware */}
            <td className="py-3 px-4 hidden xl:table-cell">
                <span className="text-xs text-dark-text-muted">v{node.firmware}</span>
            </td>

            {/* Last heartbeat */}
            <td className="py-3 px-4 hidden lg:table-cell">
                <span className="text-xs text-dark-text-muted tabular-nums">{node.last_heartbeat}</span>
            </td>

            {/* Chevron */}
            <td className="py-3 px-4 text-right">
                <svg
                    className={cn(
                        "w-4 h-4 text-dark-text-muted transition-transform duration-200 inline-block",
                        selected && "rotate-90 text-brand-400"
                    )}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
            </td>
        </tr>
    );
}
