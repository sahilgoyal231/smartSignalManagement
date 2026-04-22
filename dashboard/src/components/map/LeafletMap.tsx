"use client";

import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export type VehicleType = "AMBULANCE" | "FIRE" | "POLICE" | "DISASTER";
export type NodeStatus = "ACTIVE" | "PREEMPTING" | "OFFLINE";

export interface MockVehicle {
    id: string;
    type: VehicleType;
    label: string;
    lat: number;
    lon: number;
    speed: number;
    heading: number;
    siren: boolean;
    priority: number;
}

export interface MockNode {
    id: string;
    name: string;
    lat: number;
    lon: number;
    status: NodeStatus;
    preemptions_today: number;
    firmware: string;
}

export type FilterMode = "ALL" | "VEHICLES" | "NODES";

interface LeafletMapProps {
    filterMode: FilterMode;
    initialVehicles: MockVehicle[];
    initialNodes: MockNode[];
    onVehicleSelect?: (vehicle: MockVehicle | null) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function vehicleColor(type: VehicleType): string {
    const map: Record<VehicleType, string> = {
        AMBULANCE: "#f59e0b",
        FIRE:      "#ef4444",
        POLICE:    "#3b82f6",
        DISASTER:  "#8b5cf6",
    };
    return map[type] ?? "#f59e0b";
}

function nodeColor(status: NodeStatus): string {
    const map: Record<NodeStatus, string> = {
        ACTIVE:     "#22c55e",
        PREEMPTING: "#ef4444",
        OFFLINE:    "#64748b",
    };
    return map[status] ?? "#22c55e";
}

/** Build an HTML string for a vehicle marker. */
function buildVehicleMarkerHTML(vehicle: MockVehicle): string {
    const color = vehicleColor(vehicle.type);
    return `
        <div class="vehicle-marker-wrapper" title="${vehicle.label}">
            <div class="vehicle-pulse-ring" style="border-color:${color};"></div>
            <div class="vehicle-dot" style="background:${color};">
                <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="white" style="transform:rotate(${vehicle.heading}deg)">
                    <path d="M12 2L6 20h3v2h6v-2h3L12 2z"/>
                </svg>
            </div>
        </div>
    `;
}

/** Build an HTML string for an edge-node marker. */
function buildNodeMarkerHTML(node: MockNode): string {
    const color = nodeColor(node.status);
    return `
        <div class="node-marker-wrapper" title="${node.name}">
            <div class="node-dot" style="background:${color};box-shadow:0 0 8px ${color}88;">
                ${node.status === "PREEMPTING"
                    ? `<div class="node-pulse-ring" style="border-color:${color};"></div>`
                    : ""}
            </div>
        </div>
    `;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function LeafletMap({ filterMode, initialVehicles, initialNodes, onVehicleSelect }: LeafletMapProps) {
    const containerRef       = useRef<HTMLDivElement | null>(null);
    const mapRef             = useRef<L.Map | null>(null);
    const vehicleMarkersRef  = useRef<Map<string, L.Marker>>(new Map());
    const nodeMarkersRef     = useRef<Map<string, L.Marker>>(new Map());
    const vehicleDataRef     = useRef<MockVehicle[]>(initialVehicles.map(v => ({ ...v })));

    const [mapLoaded, setMapLoaded] = useState(false);

    // ── Mount map ─────────────────────────────────────────────────────────────
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return;

        // Initialize Map
        const map = L.map(containerRef.current, {
            zoomControl: false, // We'll position it later if needed
            attributionControl: false
        }).setView([19.052, 72.877], 12); // Lat, Lon for Mumbai

        // Dark theme OpenStreetMap tiles (CartoDB Dark Matter)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(map);
        
        L.control.zoom({ position: 'bottomleft' }).addTo(map);

        // ── Vehicle markers ───────────────────────────────────────────────
        vehicleDataRef.current.forEach(v => {
            const icon = L.divIcon({
                html: buildVehicleMarkerHTML(v),
                className: '', // prevent default leaflet styles
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });

            const marker = L.marker([v.lat, v.lon], { icon }).addTo(map);

            const popupContent = `
                <div class="map-popup">
                    <p class="map-popup-title">${v.label}</p>
                    <p class="map-popup-sub">${v.type} · Priority ${v.priority}</p>
                    <div class="map-popup-row"><span>Speed</span><span>${v.speed} km/h</span></div>
                    <div class="map-popup-row"><span>Heading</span><span>${v.heading}°</span></div>
                    <div class="map-popup-row"><span>Siren</span><span>${v.siren ? "🔴 ON" : "⚫ OFF"}</span></div>
                </div>
            `;
            marker.bindPopup(popupContent, { className: 'leaflet-popup-dark' });
            
            marker.on('click', () => onVehicleSelect?.(v));
            vehicleMarkersRef.current.set(v.id, marker);
        });

        // ── Edge-node markers ─────────────────────────────────────────────
        initialNodes.forEach(node => {
            const icon = L.divIcon({
                html: buildNodeMarkerHTML(node),
                className: '',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });

            const marker = L.marker([node.lat, node.lon], { icon }).addTo(map);

            const popupContent = `
                <div class="map-popup">
                    <p class="map-popup-title">${node.name}</p>
                    <p class="map-popup-sub">${node.id}</p>
                    <div class="map-popup-row"><span>Status</span><span>${node.status}</span></div>
                    <div class="map-popup-row"><span>Preemptions today</span><span>${node.preemptions_today}</span></div>
                    <div class="map-popup-row"><span>Firmware</span><span>v${node.firmware}</span></div>
                </div>
            `;
            marker.bindPopup(popupContent, { className: 'leaflet-popup-dark' });
            nodeMarkersRef.current.set(node.id, marker);
        });

        mapRef.current = map;
        setMapLoaded(true);

        return () => {
            map.remove();
            mapRef.current = null;
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Live WebSocket Streaming ──────────────────────────────────────────────
    useEffect(() => {
        if (!mapLoaded) return;
        
        let ws: WebSocket;
        let reconnectTimeout: NodeJS.Timeout;

        const connect = () => {
            // Event Service runs on port 8001
            ws = new WebSocket("ws://localhost:8001/api/v1/stream");

            ws.onopen = () => {
                console.log("Connected to live map stream");
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    
                    if (msg.type === "vehicle.update") {
                        const vid = msg.vehicle_id;
                        const data = msg.data;
                        
                        // Update marker position
                        const marker = vehicleMarkersRef.current.get(vid);
                        if (marker && data.location_lat && data.location_lon) {
                            marker.setLatLng([data.location_lat, data.location_lon]);
                        }
                    } else if (msg.type === "node.preempt") {
                        const nid = msg.node_id;
                        const marker = nodeMarkersRef.current.get(nid);
                        if (marker) {
                            // Visually show preemption on the marker DOM element
                            const el = marker.getElement();
                            if (el) {
                                const dot = el.querySelector(".node-dot") as HTMLElement;
                                if (dot && !el.querySelector(".node-pulse-ring")) {
                                    dot.style.background = "#ef4444";
                                    dot.style.boxShadow = "0 0 8px #ef444488";
                                    // Add pulse ring 
                                    const ring = document.createElement("div");
                                    ring.className = "node-pulse-ring";
                                    ring.style.borderColor = "#ef4444";
                                    dot.appendChild(ring);
                                }
                            }
                        }
                    } else if (msg.type === "node.heartbeat") {
                         // Optional: heartbeat handling
                    }
                } catch (e) {
                    console.error("Error parsing map stream:", e);
                }
            };

            ws.onclose = () => {
                console.log("Map stream disconnected. Reconnecting in 3s...");
                reconnectTimeout = setTimeout(connect, 3000);
            };
            
            ws.onerror = (err) => {
                console.error("Map stream error:", err);
                ws.close();
            };
        };

        connect();

        return () => {
            clearTimeout(reconnectTimeout);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        };
    }, [mapLoaded]);

    // ── Filter mode: show / hide marker layers ────────────────────────────────
    useEffect(() => {
        const showVehicles = filterMode === "ALL" || filterMode === "VEHICLES";
        const showNodes    = filterMode === "ALL" || filterMode === "NODES";

        vehicleMarkersRef.current.forEach(m => {
            const el = m.getElement();
            if (el) el.style.display = showVehicles ? "" : "none";
        });
        nodeMarkersRef.current.forEach(m => {
            const el = m.getElement();
            if (el) el.style.display = showNodes ? "" : "none";
        });
    }, [filterMode]);

    return (
        <div
            ref={containerRef}
            className="w-full h-full rounded-xl overflow-hidden bg-[#0d1117]"
            aria-label="Live Map"
        />
    );
}
