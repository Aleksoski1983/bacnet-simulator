from __future__ import annotations

import asyncio

from bacnet_lab.adapters.scenarios.base import BaseScenario
from bacnet_lab.domain.errors import ValidationError
from bacnet_lab.domain.models.scenario import ScenarioParameter


class CleanroomAhuScenario(BaseScenario):
    id = "cleanroom_ahu"
    name = "Cleanroom Supply AHU"
    description = (
        "Maintains cleanroom pressure and supply-air temperature with fan, coil, "
        "damper, and safety interlocks."
    )

    def default_parameters(self) -> list[ScenarioParameter]:
        return [
            ScenarioParameter(
                name="interval", description="Update interval in seconds", default=1.0
            ),
            ScenarioParameter(
                name="room_pressure_setpoint_pa",
                description="Room pressure setpoint in Pa",
                default=15.0,
            ),
            ScenarioParameter(
                name="supply_air_setpoint_c",
                description="Supply-air temperature setpoint in Celsius",
                default=18.0,
            ),
            ScenarioParameter(
                name="outdoor_air_damper_pct",
                description="Normal outdoor-air damper position in percent",
                default=100.0,
            ),
            ScenarioParameter(
                name="fan_rated_power_kw",
                description="Assumed rated supply fan power in kW",
                default=10.0,
            ),
        ]

    def validate(self) -> None:
        required = (
            "SupplyAirTemp",
            "SupplyAirTempSetpoint",
            "RoomDifferentialPressure",
            "FilterDifferentialPressure",
            "FanSpeed",
            "FanSpeedFeedback",
            "FanRunStatus",
            "FanFault",
            "FireAlarmStatus",
            "SupplyFanEnable",
            "OutdoorAirDamper",
            "CoolingValve",
            "HeatingValve",
            "ElectricalPower",
        )
        for point_name in required:
            self.require_point(1001, f"AHU-01/{point_name}")

        if not 0 <= self.parameter("room_pressure_setpoint_pa") <= 50:
            raise ValidationError("room_pressure_setpoint_pa must be between 0 and 50 Pa")
        if not 5 <= self.parameter("supply_air_setpoint_c") <= 35:
            raise ValidationError("supply_air_setpoint_c must be between 5 and 35 Celsius")
        if not 0 <= self.parameter("outdoor_air_damper_pct") <= 100:
            raise ValidationError("outdoor_air_damper_pct must be between 0 and 100 percent")
        if self.parameter("fan_rated_power_kw") <= 0:
            raise ValidationError("fan_rated_power_kw must be greater than zero")

    async def run(self) -> None:
        interval = float(self.parameter("interval"))
        pressure_setpoint = float(self.parameter("room_pressure_setpoint_pa"))
        supply_setpoint = float(self.parameter("supply_air_setpoint_c"))
        damper_setpoint = float(self.parameter("outdoor_air_damper_pct"))
        rated_power = float(self.parameter("fan_rated_power_kw"))
        fan_speed = float(self._device_service.point(1001, "AHU-01/FanSpeed").present_value)
        room_pressure = float(
            self._device_service.point(1001, "AHU-01/RoomDifferentialPressure").present_value
        )
        supply_temperature = float(
            self._device_service.point(1001, "AHU-01/SupplyAirTemp").present_value
        )

        while self.is_running:
            fire_alarm = bool(
                self._device_service.point(1001, "AHU-01/FireAlarmStatus").present_value
            )
            fan_fault = bool(self._device_service.point(1001, "AHU-01/FanFault").present_value)

            if fire_alarm or fan_fault:
                fan_speed = 0.0
                room_pressure += (0.0 - room_pressure) * 0.4
                fan_enabled = False
                fan_running = False
                damper_position = 0.0
                cooling_valve = 0.0
                heating_valve = 0.0
            else:
                pressure_error = pressure_setpoint - room_pressure
                fan_speed = max(0.0, min(100.0, fan_speed + pressure_error * 1.5))
                modeled_pressure = fan_speed * 0.2
                room_pressure += (modeled_pressure - room_pressure) * 0.4
                fan_enabled = True
                fan_running = True
                damper_position = damper_setpoint

                temperature_error = supply_setpoint - supply_temperature
                cooling_valve = max(0.0, min(100.0, -temperature_error * 20.0))
                heating_valve = max(0.0, min(100.0, temperature_error * 20.0))
                supply_temperature += temperature_error * 0.25

            fan_power_kw = round(rated_power * (fan_speed / 100) ** 3, 2)
            await self.write(1001, "AHU-01/SupplyAirTempSetpoint", supply_setpoint)
            await self.write(1001, "AHU-01/FanSpeed", round(fan_speed, 1))
            await self.write(1001, "AHU-01/FanSpeedFeedback", round(fan_speed, 1))
            await self.write(1001, "AHU-01/SupplyFanEnable", fan_enabled)
            await self.write(1001, "AHU-01/FanRunStatus", fan_running)
            await self.write(1001, "AHU-01/OutdoorAirDamper", round(damper_position, 1))
            await self.write(1001, "AHU-01/CoolingValve", round(cooling_valve, 1))
            await self.write(1001, "AHU-01/HeatingValve", round(heating_valve, 1))
            await self.write(1001, "AHU-01/SupplyAirTemp", round(supply_temperature, 1))
            await self.write(1001, "AHU-01/RoomDifferentialPressure", round(room_pressure, 1))
            await self.write(1001, "AHU-01/ElectricalPower", fan_power_kw)
            await asyncio.sleep(interval)
