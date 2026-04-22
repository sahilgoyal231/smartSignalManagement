"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Car, LayoutDashboard, Settings, Map as MapIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
    { name: "Overview", href: "/", icon: LayoutDashboard },
    { name: "Live Map", href: "/map", icon: MapIcon },
    { name: "Edge Nodes", href: "/nodes", icon: Activity },
    { name: "Fleet Registry", href: "/vehicles", icon: Car },
    { name: "Settings", href: "/settings", icon: Settings },
];

export default function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="w-64 flex-shrink-0 bg-dark-panel border-r border-dark-border flex flex-col pt-6 pb-4">
            {/* Brand & Logo */}
            <div className="px-6 flex items-center gap-3 mb-8">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center shadow-lg shadow-brand-500/20">
                    <Activity className="text-white w-5 h-5" strokeWidth={2.5} />
                </div>
                <div className="flex flex-col">
                    <span className="font-bold text-white tracking-tight leading-4">Smart/Signal</span>
                    <span className="text-[10px] text-dark-text-muted uppercase tracking-widest font-semibold mt-0.5">Control Center</span>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-4 space-y-1.5">
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
                    const Icon = item.icon;

                    return (
                        <Link
                            key={item.name}
                            href={item.href}
                            className={cn(
                                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group relative",
                                isActive
                                    ? "bg-dark-border text-white shadow-sm"
                                    : "text-dark-text-muted hover:bg-white/5 hover:text-white"
                            )}
                        >
                            {isActive && (
                                <div className="absolute left-0 w-1 h-5 bg-brand-500 rounded-r-full" />
                            )}
                            <Icon
                                className={cn(
                                    "w-5 h-5 transition-colors",
                                    isActive ? "text-brand-400" : "text-dark-text-muted group-hover:text-dark-text-main"
                                )}
                            />
                            {item.name}
                        </Link>
                    );
                })}
            </nav>

            {/* Footer Meta */}
            <div className="px-6 mt-auto">
                <div className="glass-card p-4 rounded-xl text-xs space-y-2">
                    <div className="flex justify-between items-center text-dark-text-muted">
                        <span>System Status</span>
                        <div className="w-2 h-2 rounded-full bg-brand-500 animate-pulse-slow" />
                    </div>
                    <div className="font-medium text-brand-100">Operational</div>
                </div>
            </div>
        </aside>
    );
}
