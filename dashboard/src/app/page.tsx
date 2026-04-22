import { Activity, Radio, ShieldAlert } from "lucide-react";
import DashboardMapWidget from "@/components/map/DashboardMapWidget";
import LiveFeed from "@/components/map/LiveFeed";

export default function OverviewPage() {
  return (
    <div className="space-y-6">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-1">System Overview</h1>
        <p className="text-dark-text-muted">Real-time status of the Smart Signal emergency preemption network.</p>
      </header>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {/* Card 1 */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Activity className="w-24 h-24" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Active Intersections</p>
          <p className="mt-2 text-3xl font-semibold text-white">42</p>
          <div className="mt-4 flex items-center text-sm">
            <span className="text-brand-500 font-medium">100% Online</span>
            <span className="ml-2 text-dark-text-muted">across Mumbai</span>
          </div>
        </div>

        {/* Card 2 */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity whitespace-nowrap">
            <Radio className="w-24 h-24 text-accent-blue" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Registered Vehicles</p>
          <p className="mt-2 text-3xl font-semibold text-white">128</p>
          <div className="mt-4 flex items-center text-sm">
            <span className="text-accent-blue font-medium">+3</span>
            <span className="ml-2 text-dark-text-muted">added this week</span>
          </div>
        </div>

        {/* Card 3 */}
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group border-accent-amber/30">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <ShieldAlert className="w-24 h-24 text-accent-amber" />
          </div>
          <p className="text-sm font-medium text-dark-text-muted">Active Preemptions</p>
          <p className="mt-2 text-3xl font-semibold text-accent-amber animate-pulse">2</p>
          <div className="mt-4 flex items-center text-sm">
            <span className="text-dark-text-muted">Live emergency routing in progress</span>
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
