/* eslint-disable react-hooks/set-state-in-effect */
"use client";

import { useEffect, useState } from "react";
import { Check, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "success" | "error" | "info";

interface ToastProps {
    message: string;
    variant?: ToastVariant;
    visible: boolean;
    onHide: () => void;
}

const ICONS: Record<ToastVariant, React.FC<{ className?: string }>> = {
    success: Check,
    error:   AlertTriangle,
    info:    Check,
};

const COLORS: Record<ToastVariant, string> = {
    success: "border-brand-500/40 bg-brand-500/10 text-brand-400",
    error:   "border-accent-red/40 bg-accent-red/10 text-accent-red",
    info:    "border-accent-blue/40 bg-accent-blue/10 text-accent-blue",
};

export default function Toast({ message, variant = "success", visible, onHide }: ToastProps) {
    const [show, setShow] = useState(false);

    useEffect(() => {
        let t1: ReturnType<typeof setTimeout>;
        let t2: ReturnType<typeof setTimeout>;
        let t3: ReturnType<typeof setTimeout>;
        if (visible) {
            t1 = setTimeout(() => setShow(true), 10);
            t2 = setTimeout(() => { 
                setShow(false); 
                t3 = setTimeout(onHide, 300); 
            }, 2800);
            return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
        } else {
            setShow(false);
        }
    }, [visible, onHide]);

    const Icon = ICONS[variant];

    return (
        <div
            className={cn(
                "fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border shadow-xl glass-panel transition-all duration-300",
                COLORS[variant],
                show ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4 pointer-events-none"
            )}
        >
            <Icon className="w-4 h-4 flex-shrink-0" />
            <span className="text-sm font-medium text-white">{message}</span>
            <button onClick={() => { setShow(false); onHide(); }} className="ml-2 text-dark-text-muted hover:text-white transition-colors">
                <X className="w-3.5 h-3.5" />
            </button>
        </div>
    );
}

// ── Hook ──────────────────────────────────────────────────────────────────────
export function useToast() {
    const [state, setState] = useState<{ message: string; variant: ToastVariant; visible: boolean }>({
        message: "", variant: "success", visible: false,
    });

    function show(message: string, variant: ToastVariant = "success") {
        setState({ message, variant, visible: true });
    }

    function hide() {
        setState(s => ({ ...s, visible: false }));
    }

    return { toast: state, show, hide };
}
