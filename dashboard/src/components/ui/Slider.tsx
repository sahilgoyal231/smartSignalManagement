"use client";

interface SliderProps {
    id?: string;
    label: string;
    value: number;
    min: number;
    max: number;
    step?: number;
    unit?: string;
    onChange: (v: number) => void;
}

export default function Slider({ id, label, value, min, max, step = 1, unit = "", onChange }: SliderProps) {
    const pct = ((value - min) / (max - min)) * 100;

    return (
        <div className="space-y-2">
            <div className="flex justify-between items-center">
                <label htmlFor={id} className="text-sm text-white font-medium">{label}</label>
                <span className="text-sm font-semibold text-brand-400 tabular-nums w-16 text-right">
                    {value}{unit}
                </span>
            </div>
            <div className="relative h-5 flex items-center">
                {/* Track */}
                <div className="w-full h-1.5 rounded-full bg-dark-border relative">
                    {/* Fill */}
                    <div
                        className="absolute inset-y-0 left-0 rounded-full bg-brand-500 transition-all"
                        style={{ width: `${pct}%` }}
                    />
                </div>
                {/* Native input (invisible, overlaid) */}
                <input
                    id={id}
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    value={value}
                    onChange={e => onChange(Number(e.target.value))}
                    className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
                />
                {/* Thumb */}
                <div
                    className="absolute w-4 h-4 rounded-full bg-white shadow-md border-2 border-brand-500 pointer-events-none transition-all"
                    style={{ left: `calc(${pct}% - 8px)` }}
                />
            </div>
            <div className="flex justify-between text-[10px] text-dark-text-muted">
                <span>{min}{unit}</span>
                <span>{max}{unit}</span>
            </div>
        </div>
    );
}
