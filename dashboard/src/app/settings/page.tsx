"use client";

import { useState, useCallback } from "react";
import { Settings, Bell, Shield, Clock, Copy, Check, RefreshCw, AlertTriangle } from "lucide-react";
import Toggle from "@/components/ui/Toggle";
import Slider from "@/components/ui/Slider";
import Toast, { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";

// ── Section wrapper ───────────────────────────────────────────────────────────

function SettingsSection({
    icon: Icon, title, description, children, onSave,
}: {
    icon: React.FC<{ className?: string }>;
    title: string;
    description: string;
    children: React.ReactNode;
    onSave: () => void;
}) {
    return (
        <div className="glass-panel rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-dark-border flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-4 h-4 text-brand-400" />
                </div>
                <div>
                    <h2 className="text-base font-semibold text-white">{title}</h2>
                    <p className="text-xs text-dark-text-muted">{description}</p>
                </div>
            </div>
            <div className="p-6 space-y-5">{children}</div>
            <div className="px-6 py-4 border-t border-dark-border/50 flex justify-end">
                <button
                    onClick={onSave}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium rounded-lg transition-colors"
                >
                    Save Changes
                </button>
            </div>
        </div>
    );
}

function FormRow({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start py-4 border-b border-dark-border/30 last:border-0 last:pb-0 first:pt-0">
            <div>
                <p className="text-sm text-white font-medium">{label}</p>
                {description && <p className="text-xs text-dark-text-muted mt-0.5">{description}</p>}
            </div>
            <div className="md:col-span-2">{children}</div>
        </div>
    );
}

function StyledInput({ id, defaultValue, type = "text", placeholder }: {
    id: string; defaultValue?: string; type?: string; placeholder?: string;
}) {
    return (
        <input
            id={id}
            type={type}
            defaultValue={defaultValue}
            placeholder={placeholder}
            className="w-full max-w-sm bg-dark-surface border border-dark-border rounded-lg px-4 py-2 text-sm text-white placeholder-dark-text-muted focus:outline-none focus:border-brand-500 transition-colors"
        />
    );
}

function StyledSelect({ id, options, defaultValue }: { id: string; options: string[]; defaultValue?: string }) {
    return (
        <select
            id={id}
            defaultValue={defaultValue}
            className="w-full max-w-sm bg-dark-surface border border-dark-border rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
        >
            {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
    );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function SettingsPage() {
    const { toast, show: showToast, hide: hideToast } = useToast();

    // General
    const [city, setCity]  = useState("Mumbai");
    const [operator, setOperator] = useState("Admin Operator");
    const [timezone, setTimezone] = useState("Asia/Kolkata");
    const [units, setUnits] = useState("Metric");

    // Signal timing
    const [preemptThreshold, setPreemptThreshold] = useState(45);
    const [maxGreenHold, setMaxGreenHold]         = useState(60);
    const [alertThreshold, setAlertThreshold]     = useState(90);

    // Notifications
    const [emailAlerts, setEmailAlerts] = useState(true);
    const [smsAlerts, setSmsAlerts]     = useState(false);
    const [faultAlerts, setFaultAlerts] = useState(true);
    const [preemptAlerts, setPreemptAlerts] = useState(true);
    const [severity, setSeverity] = useState("HIGH");

    // Security
    const [copiedKey, setCopiedKey] = useState(false);
    const MOCK_API_KEY = "sss_live_k3y_4X9mNpQrT7vWxYzAbCdEfGhIjKlMnOpQrStUv";
    const tokenExpiry = "2026-09-11";

    const copyKey = useCallback(() => {
        navigator.clipboard.writeText(MOCK_API_KEY).catch(() => {});
        setCopiedKey(true);
        setTimeout(() => setCopiedKey(false), 2000);
    }, []);

    function save(section: string) {
        showToast(`${section} settings saved`, "success");
    }

    return (
        <div className="space-y-5 max-w-3xl mx-auto">
            <header className="mb-2">
                <h1 className="text-3xl font-bold tracking-tight text-white mb-1">System Settings</h1>
                <p className="text-dark-text-muted">Global configuration for the Smart Signal Control Center.</p>
            </header>

            {/* ── 1. General ────────────────────────────────────────────────── */}
            <SettingsSection
                icon={Settings}
                title="General"
                description="Core operational parameters for this deployment"
                onSave={() => save("General")}
            >
                <FormRow label="City" description="Primary operational sector">
                    <StyledInput id="setting-city" defaultValue={city} />
                </FormRow>
                <FormRow label="Operator Name" description="Displayed in reports and alerts">
                    <StyledInput id="setting-operator" defaultValue={operator} />
                </FormRow>
                <FormRow label="Timezone">
                    <StyledSelect
                        id="setting-timezone"
                        defaultValue={timezone}
                        options={["Asia/Kolkata", "Asia/Dubai", "UTC", "Asia/Singapore", "Europe/London"]}
                    />
                </FormRow>
                <FormRow label="Units">
                    <StyledSelect
                        id="setting-units"
                        defaultValue={units}
                        options={["Metric (km, m/s)", "Imperial (mi, mph)"]}
                    />
                </FormRow>
            </SettingsSection>

            {/* ── 2. Signal Timing ──────────────────────────────────────────── */}
            <SettingsSection
                icon={Clock}
                title="Signal Timing"
                description="Defaults applied to all edge nodes unless overridden per-node"
                onSave={() => save("Signal Timing")}
            >
                <FormRow
                    label="Preempt Threshold"
                    description="ETA at which green is extended for an approaching vehicle"
                >
                    <div className="max-w-sm">
                        <Slider
                            id="setting-preempt-threshold"
                            label=""
                            value={preemptThreshold}
                            min={15}
                            max={120}
                            step={5}
                            unit="s"
                            onChange={setPreemptThreshold}
                        />
                    </div>
                </FormRow>
                <FormRow
                    label="Max Green Hold"
                    description="Maximum time to keep green during active preemption"
                >
                    <div className="max-w-sm">
                        <Slider
                            id="setting-max-green-hold"
                            label=""
                            value={maxGreenHold}
                            min={20}
                            max={120}
                            step={5}
                            unit="s"
                            onChange={setMaxGreenHold}
                        />
                    </div>
                </FormRow>
                <FormRow
                    label="Alert Threshold"
                    description="When to send an upstream alert if vehicle hasn't cleared"
                >
                    <div className="max-w-sm">
                        <Slider
                            id="setting-alert-threshold"
                            label=""
                            value={alertThreshold}
                            min={30}
                            max={180}
                            step={10}
                            unit="s"
                            onChange={setAlertThreshold}
                        />
                    </div>
                </FormRow>
            </SettingsSection>

            {/* ── 3. Notifications ──────────────────────────────────────────── */}
            <SettingsSection
                icon={Bell}
                title="Notifications"
                description="Configure alert channels and minimum severity"
                onSave={() => save("Notifications")}
            >
                <FormRow label="Email Alerts" description="Send critical alerts to on-call email">
                    <Toggle
                        id="toggle-email"
                        checked={emailAlerts}
                        onChange={setEmailAlerts}
                    />
                </FormRow>
                <FormRow label="SMS Alerts" description="Text message fallback for Priority 1 events">
                    <Toggle
                        id="toggle-sms"
                        checked={smsAlerts}
                        onChange={setSmsAlerts}
                    />
                </FormRow>
                <FormRow label="Fault Notifications" description="Node hardware failures and connectivity drops">
                    <Toggle
                        id="toggle-faults"
                        checked={faultAlerts}
                        onChange={setFaultAlerts}
                    />
                </FormRow>
                <FormRow label="Preemption Events" description="Notify on each triggered signal preemption">
                    <Toggle
                        id="toggle-preemptions"
                        checked={preemptAlerts}
                        onChange={setPreemptAlerts}
                    />
                </FormRow>
                <FormRow label="Minimum Severity" description="Only alert above this severity floor">
                    <StyledSelect
                        id="setting-severity"
                        defaultValue={severity}
                        options={["LOW", "MEDIUM", "HIGH", "CRITICAL"]}
                    />
                </FormRow>
            </SettingsSection>

            {/* ── 4. Security & Tokens ──────────────────────────────────────── */}
            <SettingsSection
                icon={Shield}
                title="Security & API Tokens"
                description="Manage API credentials and token rotation"
                onSave={() => save("Security")}
            >
                <FormRow label="API Key" description="Used by the dashboard to authenticate with cloud services">
                    <div className="flex items-center gap-2 max-w-sm">
                        <div className="flex-1 bg-dark-surface border border-dark-border rounded-lg px-3 py-2 flex items-center justify-between gap-2 min-w-0">
                            <span className="font-mono text-xs text-dark-text-muted truncate">{MOCK_API_KEY.slice(0, 28)}…</span>
                            <button
                                id="copy-api-key"
                                onClick={copyKey}
                                className="text-dark-text-muted hover:text-brand-400 transition-colors flex-shrink-0"
                                title="Copy API key"
                            >
                                {copiedKey ? <Check className="w-3.5 h-3.5 text-brand-500" /> : <Copy className="w-3.5 h-3.5" />}
                            </button>
                        </div>
                    </div>
                </FormRow>
                <FormRow label="Token Expiry" description="After this date the token must be rotated">
                    <div className="flex items-center gap-3">
                        <span className="font-mono text-sm text-white">{tokenExpiry}</span>
                        <span className="text-xs text-accent-amber font-medium">Expires in 182 days</span>
                    </div>
                </FormRow>
                <FormRow label="Regenerate Token" description="Invalidates the current token immediately">
                    <button
                        id="regenerate-token-btn"
                        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-accent-red/30 bg-accent-red/10 text-accent-red hover:bg-accent-red/20 transition-colors"
                        onClick={() => showToast("Token regeneration requires 2FA confirmation", "error")}
                    >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Regenerate API Key
                    </button>
                </FormRow>
                <FormRow label="TLS Version" description="All edge-node connections encrypted with">
                    <div className="flex items-center gap-2">
                        <span className="text-sm text-white font-medium font-mono">TLS 1.3</span>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-500/15 text-brand-400">Enforced</span>
                    </div>
                </FormRow>
                <div className="mt-2 flex items-start gap-2 p-3 rounded-lg bg-accent-amber/5 border border-accent-amber/20">
                    <AlertTriangle className="w-4 h-4 text-accent-amber flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-accent-amber/80">
                        Rotating the API key will disconnect all active edge-node sessions. Schedule during a maintenance window.
                    </p>
                </div>
            </SettingsSection>

            {/* Toast */}
            <Toast message={toast.message} variant={toast.variant} visible={toast.visible} onHide={hideToast} />
        </div>
    );
}
