"use client";

import { cn } from "@/lib/utils";

interface ToggleProps {
    id?: string;
    checked: boolean;
    onChange: (v: boolean) => void;
    label?: string;
    description?: string;
    disabled?: boolean;
}

export default function Toggle({ id, checked, onChange, label, description, disabled }: ToggleProps) {
    return (
        <label
            htmlFor={id}
            className={cn(
                "flex items-start justify-between gap-4 cursor-pointer select-none group",
                disabled && "opacity-50 cursor-not-allowed"
            )}
        >
            {(label || description) && (
                <div>
                    {label && <p className="text-sm text-white font-medium group-hover:text-white">{label}</p>}
                    {description && <p className="text-xs text-dark-text-muted mt-0.5">{description}</p>}
                </div>
            )}
            <button
                id={id}
                role="switch"
                aria-checked={checked}
                disabled={disabled}
                onClick={() => !disabled && onChange(!checked)}
                className={cn(
                    "relative w-10 h-5 rounded-full transition-colors duration-200 flex-shrink-0 mt-0.5 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 focus:ring-offset-dark-panel",
                    checked ? "bg-brand-500" : "bg-dark-border"
                )}
            >
                <span
                    className={cn(
                        "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200",
                        checked && "translate-x-5"
                    )}
                />
            </button>
        </label>
    );
}
