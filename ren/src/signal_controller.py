"""
Signal Controller Interface
===========================
Abstracts the physical connection to the traffic signal controller.
"""
from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger

from ren.src.config import RENConfig


class BaseSignalController(ABC):
    def __init__(self, config: RENConfig):
        self._cfg = config
        self._active_phase: Optional[str] = None

    @abstractmethod
    def set_preemption(self, phase: str) -> bool:
        """Triggers preemption for the specified phase. Returns True on success."""
        pass

    @abstractmethod
    def clear_preemption(self) -> bool:
        """Clears any active preemption and returns to normal operation."""
        pass


class MockSignalController(BaseSignalController):
    def set_preemption(self, phase: str) -> bool:
        if self._active_phase != phase:
            logger.info(f"[MOCK CONTROLLER] Setting signal to GREEN for {phase}. ALL RED for others.")
            self._active_phase = phase
        return True

    def clear_preemption(self) -> bool:
        if self._active_phase is not None:
            logger.info("[MOCK CONTROLLER] Clearing preemption. Reverting to NORMAL phase plan.")
            self._active_phase = None
        return True


class RelaySignalController(BaseSignalController):
    def __init__(self, config: RENConfig):
        super().__init__(config)
        self.pin_ns = config.relay_pin_ns
        self.pin_ew = config.relay_pin_ew
        self._setup_gpio()

    def _setup_gpio(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)
            self.GPIO.setup(self.pin_ns, self.GPIO.OUT, initial=self.GPIO.LOW)
            self.GPIO.setup(self.pin_ew, self.GPIO.OUT, initial=self.GPIO.LOW)
            logger.info(f"Relay Controller initialized on pins NS:{self.pin_ns}, EW:{self.pin_ew}")
        except ImportError:
            logger.warning("RPi.GPIO not found. Relay controller will not physically toggle pins.")
            self.GPIO = None

    def set_preemption(self, phase: str) -> bool:
        if self._active_phase == phase:
            return True
            
        logger.info(f"Triggering RELAY for phase {phase}")
        self._active_phase = phase
        
        if self.GPIO is None:
            return True
            
        if phase == "PHASE_NORTH_SOUTH":
            self.GPIO.output(self.pin_ns, self.GPIO.HIGH)
            self.GPIO.output(self.pin_ew, self.GPIO.LOW)
        elif phase == "PHASE_EAST_WEST":
            self.GPIO.output(self.pin_ns, self.GPIO.LOW)
            self.GPIO.output(self.pin_ew, self.GPIO.HIGH)
        return True

    def clear_preemption(self) -> bool:
        if self._active_phase is not None:
            logger.info("Clearing RELAY preemption. All relays OFF.")
            self._active_phase = None
            if self.GPIO is not None:
                self.GPIO.output(self.pin_ns, self.GPIO.LOW)
                self.GPIO.output(self.pin_ew, self.GPIO.LOW)
        return True


class SerialSignalController(BaseSignalController):
    def __init__(self, config: RENConfig):
        super().__init__(config)
        self.port = config.controller_serial_port
        self.baud = config.controller_serial_baud
        self.serial = None
        self._connect()

    def _connect(self):
        try:
            import serial
            self.serial = serial.Serial(self.port, self.baud, timeout=1)
            logger.info(f"Serial Controller connected on {self.port} at {self.baud} baud")
        except ImportError:
            logger.warning("pyserial not found. Serial commands won't be sent.")
        except Exception as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")

    def _send_command(self, cmd: str) -> bool:
        if self.serial and self.serial.is_open:
            try:
                self.serial.write(f"{cmd}\n".encode('utf-8'))
                return True
            except Exception as e:
                logger.error(f"Serial write error: {e}")
                return False
        return False

    def set_preemption(self, phase: str) -> bool:
        if self._active_phase == phase:
            return True
            
        logger.info(f"Sending SERIAL command for phase {phase}")
        self._active_phase = phase
        return self._send_command(f"PREEMPT {phase}")

    def clear_preemption(self) -> bool:
        if self._active_phase is not None:
            logger.info("Sending SERIAL clear command")
            self._active_phase = None
            return self._send_command("CLEAR")
        return True


def get_signal_controller(config: RENConfig) -> BaseSignalController:
    """Factory to instantiate the configured controller type."""
    ctype = config.controller_type.upper()
    if ctype == "RELAY":
        return RelaySignalController(config)
    elif ctype == "SERIAL":
        return SerialSignalController(config)
    else:
        return MockSignalController(config)
