"use client";

import { useState, useEffect } from "react";
import { Activity, Radio, ShieldAlert, AlertTriangle, CheckCircle, Clock } from "lucide-react";
import DashboardMapWidget from "@/components/map/DashboardMapWidget";
import LiveFeed from "@/components/map/LiveFeed";
import { API } from "@/lib/api";

interface DashboardStats {
  totalNodes: number;
  onlineNodes: number;
  offlineNodes: number;
  totalVehicles: number;
  activeVehicles: number;
  totalEvents: number;
  clearedEvents: number;
  activePreemptions: number;
}

export default function OverviewPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const [vRes, nRes, eRes] = await Promise.all([
          fetch(`${API.VEHICLE_REGISTRY}/api/v1/vehicles?active_only=false`),
          fetch(`${API.EDGE_REGISTRY}/api/v1/nodes`),
          fetch(`${API.EVENT_SERVICE}/api/v1/events`),
        ]);

        const vehicles = await vRes.json();
        const nodes = await nRes.json();
        const events = await eRes.json();

        const onlineNodes = nodes.filter((n: any) => n.is_online).length;
        const activeVehicles = vehicles.filter((v: any) => v.is_active).length;
        const clearedEvents = events.filter((e: any) => e.outcome === "CLEARED").length;
        // Count events that happened in the last hour as "active preemptions"
        const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
        const activePreemptions = events.filter((e: any) => {
          const t = new Date(e.triggered_at);
          return t > oneHourAgo && !e.cleared_at;
        }).length;

        setStats({
          totalNodes: nodes.length,
          onlineNodes,
          offlineNodes: nodes.length - onlineNodes,
          totalVehicles: vehicles.length,
          activeVehicles,
          totalEvents: events.length,
          clearedEvents,
          activePreemptions,
        });
      } catch (e) {
        console.error("Failed to fetch dashboard stats:", e);
        setStats({
          totalNodes: 0, onlineNodes: 0, offlineNodes: 0,
          totalVehicles: 0, activeVehicles: 0,
          totalEvents: 0, clearedEvents: 0, activePreemptions: 0,
        });
      } finally {
        setIsLoading(false);
      }
    }
    fetchStats();
    const interval = setInterval(fetchStats, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const s = stats;

  return (
    <div className="space-y-6">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-1">System Overview</h1>
        <p className="text-dark-text-muted">Real-time status of the Smart Signal emergency preemption network.</p>
      </header>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: Intersections */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Activity className="w-24 h-24" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Active Intersections</p>
          {isLoading ? (
            <div className="mt-2 h-9 w-16 bg-dark-border/50 rounded animate-pulse" />
          ) : (
            <p className="mt-2 text-3xl font-semibold text-white">{s?.onlineNodes}</p>
          )}
          <div className="mt-4 flex items-center text-sm">
            <span className="text-brand-500 font-medium">
              {s ? Math.round((s.onlineNodes / Math.max(s.totalNodes, 1)) * 100) : 0}% Online
            </span>
            <span className="ml-2 text-dark-text-muted">of {s?.totalNodes} nodes</span>
          </div>
        </div>

        {/* Card 2: Fleet */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity whitespace-nowrap">
            <Radio className="w-24 h-24 text-accent-blue" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Registered Vehicles</p>
          {isLoading ? (
            <div className="mt-2 h-9 w-16 bg-dark-border/50 rounded animate-pulse" />
          ) : (
            <p className="mt-2 text-3xl font-semibold text-white">{s?.totalVehicles}</p>
          )}
          <div className="mt-4 flex items-center text-sm">
            <span className="text-accent-blue font-medium">{s?.activeVehicles} active</span>
            <span className="ml-2 text-dark-text-muted">across Mumbai</span>
          </div>
        </div>

        {/* Card 3: Active Preemptions */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group border-accent-amber/30">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <ShieldAlert className="w-24 h-24 text-accent-amber" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Total Preemptions</p>
          {isLoading ? (
            <div className="mt-2 h-9 w-16 bg-dark-border/50 rounded animate-pulse" />
          ) : (
            <p className="mt-2 text-3xl font-semibold text-white">{s?.totalEvents}</p>
          )}
          <div className="mt-4 flex items-center text-sm">
            <span className="text-accent-amber font-medium">{s?.activePreemptions} in progress</span>
            <span className="ml-2 text-dark-text-muted">last 7 days</span>
          </div>
        </div>

        {/* Card 4: Success Rate */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <CheckCircle className="w-24 h-24 text-brand-500" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Clearance Rate</p>
          {isLoading ? (
            <div className="mt-2 h-9 w-16 bg-dark-border/50 rounded animate-pulse" />
          ) : (
            <p className="mt-2 text-3xl font-semibold text-brand-500">
              {s && s.totalEvents > 0 ? Math.round((s.clearedEvents / s.totalEvents) * 100) : 0}%
            </p>
          )}
          <div className="mt-4 flex items-center text-sm">
            <span className="text-brand-500 font-medium">{s?.clearedEvents} cleared</span>
            <span className="ml-2 text-dark-text-muted">of {s?.totalEvents} total</span>
          </div>
        </div>
      </div>

      {/* Map and Feed */}
      <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass-panel rounded-xl min-h-[400px] overflow-hidden">
          <DashboardMapWidget />
        </div>

        <div className="glass-panel rounded-xl h-[400px] p-4 flex flex-col">
          <LiveFeed />
        </div>
      </div>
    </div>
  );
}
