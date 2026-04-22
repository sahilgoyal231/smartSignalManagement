"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { MockVehicle, MockNode, VehicleType } from "./LeafletMap";

const LeafletMap = dynamic(() => import("./LeafletMap"), {
    ssr: false,
    loading: () => (
        <div className="w-full h-full flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-dark-text-muted text-sm">Loading map...</p>
            </div>
        </div>
    ),
});

export default function DashboardMapWidget() {
    const [vehicles, setVehicles] = useState<MockVehicle[]>([]);
    const [nodes, setNodes] = useState<MockNode[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        async function fetchInitialData() {
            try {
                const vRes = await fetch('http://localhost:8006/api/v1/vehicles');
                const vData = await vRes.json();
                
                const nRes = await fetch('http://localhost:8002/api/v1/nodes');
                const nData = await nRes.json();
                
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
                
                const mappedNodes: MockNode[] = nData.map((n: any) => ({
                    id: n.node_id,
                    name: n.intersection_name,
                    lat: parseFloat(n.location_lat || "0"),
                    lon: parseFloat(n.location_lon || "0"),
                    status: n.is_online ? "ACTIVE" : "OFFLINE",
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

    if (isLoading) {
        return (
            <div className="w-full h-full flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <LeafletMap
            filterMode="ALL"
            initialVehicles={vehicles}
            initialNodes={nodes}
        />
    );
}
