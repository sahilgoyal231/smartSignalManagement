"""
Siren Detector — Automatic Emergency Activation
=================================================
Detects active siren state using two independent methods:
  1. Digital GPIO trigger  — high signal from analog comparator circuit
     (microphone → LM393 comparator → GPIO17 HIGH when siren detected)
  2. FFT frequency analysis — software fallback using USB microphone + scipy
     Detects characteristic siren frequency sweep 500 Hz – 2 kHz

Both methods are debounced — siren must persist for `hold_s` seconds
(default 0.5s) before activating, preventing false triggers.

The SirenDetector runs as a background thread and exposes a single
thread-safe method: is_siren_active() → bool

Hardware path (GPIO):
    Microphone → LM393 analogue comparator → GPIO17 (BCM)
    When siren amplitude exceeds Vref: GPIO17 goes HIGH
    VSU sampling rate: 100 Hz (10ms polling loop)

Software path (FFT fallback):
    USB microphone → PyAudio → 1024-sample FFT every 50ms
    Detects energy peak in 500–2000 Hz band above threshold
    Auto-selected when RPi.GPIO is unavailable

State machine:
  IDLE      →  DETECTED (siren signal present) →  ACTIVE (held > 0.5s)
  ACTIVE    →  CLEARING (signal lost)          →  IDLE   (held clear > 0.5s)
"""
from __future__ import annotations

import threading
import time
from enum import Enum, auto
from typing import Optional

from loguru import logger


class SirenState(Enum):
    IDLE     = auto()
    DETECTED = auto()
    ACTIVE   = auto()
    CLEARING = auto()


class SirenDetector:
    """
    Background thread that monitors for active siren.

    Usage:
        det = SirenDetector(config)
        det.start()
        active = det.is_siren_active()   # thread-safe
        det.stop()
    """

    POLL_HZ      = 100      # GPIO polling rate (10ms per cycle)
    FFT_SAMPLES  = 1024     # Audio samples per FFT frame
    FFT_RATE_HZ  = 16000    # USB mic sample rate

    def __init__(self, config) -> None:
        self._cfg     = config
        self._state   = SirenState.IDLE
        self._lock    = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._method  = "none"

        # Debounce timers
        self._detected_at: Optional[float] = None
        self._clearing_at: Optional[float] = None

        # Stats
        self._activation_count = 0
        self._total_active_s   = 0.0
        self._activated_at: Optional[float] = None

        # Hardware handles
        self._gpio       = None
        self._audio      = None
        self._audio_stream = None

    # ─────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────

    def start(self) -> None:
        self._method = self._init_hardware()
        self._running = True
        self._thread  = threading.Thread(
            target=self._detection_loop, daemon=True, name="siren-detector"
        )
        self._thread.start()
        logger.info(f"SirenDetector: Started — method={self._method}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
        if self._audio:
            try:
                self._audio.terminate()
            except Exception:
                pass
        logger.info(
            f"SirenDetector: Stopped — activations={self._activation_count} "
            f"total_active={self._total_active_s:.1f}s"
        )

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def is_siren_active(self) -> bool:
        with self._lock:
            return self._state == SirenState.ACTIVE

    def get_state(self) -> SirenState:
        with self._lock:
            return self._state

    def stats(self) -> dict:
        return {
            "state":            self._state.name,
            "method":           self._method,
            "activations":      self._activation_count,
            "total_active_s":   round(self._total_active_s, 1),
        }

    # ─────────────────────────────────────────────
    # Hardware init
    # ─────────────────────────────────────────────

    def _init_hardware(self) -> str:
        """Try GPIO → FFT → mock in order of preference."""

        # ── Try GPIO ────────────────────────────────────
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._cfg.siren_gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            self._gpio = GPIO
            logger.success(
                f"SirenDetector: GPIO mode — pin BCM{self._cfg.siren_gpio_pin}"
            )
            return "gpio"
        except (ImportError, RuntimeError):
            pass

        # ── Try FFT via PyAudio ──────────────────────────
        try:
            import pyaudio                        # type: ignore
            import numpy as np                    # type: ignore
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.FFT_RATE_HZ,
                input=True,
                frames_per_buffer=self.FFT_SAMPLES,
            )
            self._audio        = pa
            self._audio_stream = stream
            logger.success("SirenDetector: FFT/audio mode — USB microphone")
            return "fft"
        except Exception:
            pass

        # ── Mock fallback ───────────────────────────────
        logger.warning(
            "SirenDetector: No hardware available — MOCK mode "
            "(siren simulates ON at t+5s, OFF at t+15s)"
        )
        self._mock_start = time.monotonic()
        return "mock"

    # ─────────────────────────────────────────────
    # Detection loop
    # ─────────────────────────────────────────────

    def _detection_loop(self) -> None:
        if self._method == "gpio":
            self._gpio_loop()
        elif self._method == "fft":
            self._fft_loop()
        else:
            self._mock_loop()

    # ── GPIO path ────────────────────────────────

    def _gpio_loop(self) -> None:
        GPIO = self._gpio
        pin  = self._cfg.siren_gpio_pin

        while self._running:
            raw_signal = GPIO.input(pin)
            self._update_state(bool(raw_signal))
            time.sleep(1 / self.POLL_HZ)

        GPIO.cleanup()

    # ── FFT path ─────────────────────────────────

    def _fft_loop(self) -> None:
        import numpy as np   # type: ignore

        low  = self._cfg.siren_freq_low_hz
        high = self._cfg.siren_freq_high_hz
        freqs = np.fft.rfftfreq(self.FFT_SAMPLES, d=1.0 / self.FFT_RATE_HZ)
        band_mask = (freqs >= low) & (freqs <= high)

        THRESHOLD = 0.25   # fraction of max power in siren band to trigger

        while self._running:
            try:
                raw = self._audio_stream.read(
                    self.FFT_SAMPLES, exception_on_overflow=False
                )
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                fft_mag = np.abs(np.fft.rfft(samples))

                band_energy  = fft_mag[band_mask].mean()
                total_energy = fft_mag.mean() + 1e-9
                ratio = band_energy / total_energy

                signal_present = ratio > THRESHOLD
                self._update_state(signal_present)

                logger.debug(
                    f"SirenFFT: band_ratio={ratio:.3f} "
                    f"threshold={THRESHOLD} "
                    f"→ {'DETECTED' if signal_present else 'quiet'}"
                )

            except Exception as exc:
                logger.warning(f"SirenFFT: Audio read error — {exc}")
                time.sleep(0.1)

    # ── Mock path ─────────────────────────────────

    def _mock_loop(self) -> None:
        """Simulates: quiet for 5s → siren ON for 10s → quiet for 10s → repeat."""
        while self._running:
            elapsed = (time.monotonic() - self._mock_start) % 25
            siren_on = 5 <= elapsed < 15
            self._update_state(siren_on)
            time.sleep(0.1)

    # ─────────────────────────────────────────────
    # State machine: debounced transition
    # ─────────────────────────────────────────────

    def _update_state(self, signal_present: bool) -> None:
        """
        Debounced state machine:
          IDLE → DETECTED (signal arrives) → ACTIVE (held > hold_s)
          ACTIVE → CLEARING (signal gone) → IDLE (cleared > hold_s)
        """
        now   = time.monotonic()
        hold  = self._cfg.siren_hold_s

        with self._lock:
            if self._state == SirenState.IDLE:
                if signal_present:
                    self._state       = SirenState.DETECTED
                    self._detected_at = now

            elif self._state == SirenState.DETECTED:
                if not signal_present:
                    self._state       = SirenState.IDLE   # Transient — reset
                    self._detected_at = None
                elif now - self._detected_at >= hold:
                    self._state        = SirenState.ACTIVE
                    self._activated_at = now
                    self._activation_count += 1
                    logger.info(
                        f"🚨 Siren ACTIVATED (activation #{self._activation_count})"
                    )

            elif self._state == SirenState.ACTIVE:
                if not signal_present:
                    self._state       = SirenState.CLEARING
                    self._clearing_at = now
                    if self._activated_at:
                        self._total_active_s += now - self._activated_at

            elif self._state == SirenState.CLEARING:
                if signal_present:
                    self._state       = SirenState.ACTIVE   # Signal returned
                    self._activated_at = now
                elif now - self._clearing_at >= hold:
                    self._state = SirenState.IDLE
                    logger.info("Siren deactivated — returning to IDLE")
