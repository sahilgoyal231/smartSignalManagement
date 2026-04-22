"use client";

import { useEffect, useRef, useState } from "react";
import { VehicleType } from "@/components/map/LeafletMap";

export interface MockEvent {
    id: string;
    ts: string;
    vehicleId: string;
    vehicleType: VehicleType;
    nodeName: string;
    eta_s: number;
    outcome: "IN_PROGRESS" | "CLEARED" | "ABORTED";
}
import { cn } from "@/lib/utils";

// ── Helpers ───────────────────────────────────────────────────────────────────

const VEHICLE_TYPE_LABEL: Record<VehicleType, string> = {
    AMBULANCE: "🚑",
    FIRE:      "🚒",
    POLICE:    "🚔",
    DISASTER:  "🚐",
};

const OUTCOME_STYLES = {
    IN_PROGRESS: "text-amber-400 font-semibold",
    CLEARED:     "text-brand-500",
    ABORTED:     "text-accent-red",
};

const OUTCOME_LABELS = {
    IN_PROGRESS: "In Progress",
    CLEARED:     "Cleared",
    ABORTED:     "Aborted",
};

export default function LiveFeed() {
    const [events, setEvents] = useState<MockEvent[]>([]);

    useEffect(() => {
        let ws: WebSocket;
        let reconnectTimeout: NodeJS.Timeout;

        const connect = () => {
            ws = new WebSocket("ws://localhost:8001/api/v1/stream");

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    
                    if (msg.type === "node.preempt") {
                        const data = msg.data;
                        const now = new Date();
                        const ts = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}:${String(now.getSeconds()).padStart(2,"0")}`;
                        
                        const newEvt: MockEvent = {
                            id: `EVT-${data.event_id || Date.now()}`,
                            ts,
                            vehicleId: data.vehicle_id || "Unknown",
                            vehicleType: "AMBULANCE", // Default fallback if not provided in payload
                            nodeName: data.target_node_id || msg.node_id,
                            eta_s: Math.round(data.eta_s || 0),
                            outcome: "IN_PROGRESS",
                        };

                        setEvents(prev => [newEvt, ...prev].slice(0, 20));
                    }
                } catch (e) {
                    console.error("Error parsing live feed:", e);
                }
            };

            ws.onclose = () => {
                reconnectTimeout = setTimeout(connect, 3000);
            };
            
            ws.onerror = () => ws.close();
        };

        connect();

        return () => {
            clearTimeout(reconnectTimeout);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        };
    }, []);

    return (
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between mb-4 flex-shrink-0">
                <h2 className="font-semibold text-white text-sm tracking-wide uppercase">Live Events</h2>
                <span className="flex items-center gap-1.5 text-xs text-brand-500 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
                    Live
                </span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                {events.map((evt, idx) => (
                    <div
                        key={evt.id}
                        className={cn(
                            "glass-card rounded-lg p-3 border-l-2 transition-all duration-500",
                            evt.outcome === "IN_PROGRESS"
                                ? "border-amber-400 animate-slide-in"
                                : evt.outcome === "CLEARED"
                                ? "border-brand-500/50"
                                : "border-accent-red/40",
                            idx === 0 ? "ring-1 ring-white/5" : ""
                        )}
                        style={{ animationDelay: `${idx * 30}ms` }}
                    >
                        <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-1.5 min-w-0">
                                <span className="text-sm flex-shrink-0">{VEHICLE_TYPE_LABEL[evt.vehicleType]}</span>
                                <span className="text-white text-xs font-mono font-semibold truncate">
                                    {evt.vehicleId}
                                </span>
                            </div>
                            <span className="text-dark-text-muted text-[10px] flex-shrink-0 tabular-nums mt-0.5">
                                {evt.ts}
                            </span>
                        </div>

                        <p className="text-dark-text-muted text-xs mt-1 truncate">{evt.nodeName}</p>

                        <div className="flex items-center justify-between mt-2">
                            <span className={cn("text-xs", OUTCOME_STYLES[evt.outcome])}>
                                {OUTCOME_LABELS[evt.outcome]}
                            </span>
                            {evt.outcome === "IN_PROGRESS" && (
                                <span className="text-[10px] text-amber-400/80 tabular-nums">
                                    ETA {evt.eta_s}s
                                </span>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
