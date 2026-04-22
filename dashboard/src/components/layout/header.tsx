import { Bell, Search, User } from "lucide-react";

export default function Header() {
    return (
        <header className="h-16 flex-shrink-0 border-b border-dark-border bg-dark-surface/50 backdrop-blur-md flex items-center justify-between px-6 lg:px-8 z-10 sticky top-0">
            <div className="flex items-center gap-4 flex-1">
                <div className="relative w-full max-w-md hidden md:block">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Search className="h-4 w-4 text-dark-text-muted" />
                    </div>
                    <input
                        type="text"
                        className="block w-full pl-10 pr-3 py-2 border border-dark-border rounded-lg leading-5 bg-dark-panel text-dark-text-main placeholder-dark-text-muted focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 sm:text-sm transition-shadow"
                        placeholder="Search intersections, vehicles, or alerts..."
                    />
                </div>
            </div>

            <div className="flex items-center gap-4">
                {/* Notification Bell */}
                <button className="relative p-2 text-dark-text-muted hover:text-white transition-colors rounded-lg hover:bg-white/5">
                    <span className="absolute top-1.5 right-1.5 block h-2 w-2 rounded-full bg-accent-red ring-2 ring-dark-surface" />
                    <Bell className="w-5 h-5" />
                </button>

                {/* User Profile */}
                <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-brand-600 to-accent-blue flex items-center justify-center border border-white/10 cursor-pointer shadow-sm">
                    <User className="h-4 w-4 text-white" />
                </div>
            </div>
        </header>
    );
}
