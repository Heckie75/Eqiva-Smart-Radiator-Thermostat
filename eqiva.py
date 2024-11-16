#!/usr/bin/python3
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

from bleak import (AdvertisementData, BleakClient, BleakError, BleakScanner,
                   BLEDevice)

_MAX_BLE_CONNECTIONS = 8


class MyLogger():

    LEVELS = {
        "DEBUG": 0,
        "INFO": 1,
        "WARN": 2,
        "ERROR": 3
    }

    NAMES = ["DEBUG", "INFO", "WARN", "ERROR"]

    def __init__(self, level: int) -> None:

        self.level = level

    def error(self, s: str):

        self.log(MyLogger.LEVELS["ERROR"], s)

    def warning(self, s: str):

        self.log(MyLogger.LEVELS["WARN"], s)

    def info(self, s: str):

        self.log(MyLogger.LEVELS["INFO"], s)

    def debug(self, s: str):

        self.log(MyLogger.LEVELS["DEBUG"], s)

    def log(self, level: int, s: str):

        if level >= self.level:
            print(f"{MyLogger.NAMES[level]}\t{s}", file=sys.stderr, flush=True)

    @staticmethod
    def hexstr(ba: bytearray) -> str:

        return " ".join([("0" + hex(b).replace("0x", ""))[-2:] for b in ba])


LOGGER = MyLogger(level=MyLogger.LEVELS["WARN"])


class EqivaException(Exception):

    def __init__(self, message) -> None:

        self.message = message


class Temperature:

    def __init__(self, valueC: float = None):

        self.valueC: float = valueC

    @staticmethod
    def fromByte(raw: int) -> 'Temperature':

        t = Temperature()
        t.valueC = raw / 2
        return t

    def toByte(self) -> int:

        return int(self.valueC * 2)

    def fahrenheit(self) -> float:

        return (self.valueC * 9.0/5.0) + 32.0

    def to_dict(self) -> dict:

        return {
            "valueC": self.valueC,
            "valueF": self.fahrenheit()
        }

    def __str__(self):

        return f"Temperature(celcius={self.valueC:.1f}°C, fahrenheit={self.fahrenheit():.1f}°F)"


class Event():

    def __init__(self, temperature: Temperature = None, hour: int = 0, minute: int = 0):

        self.hour = hour
        self.minute = minute
        self.temperature: Temperature = temperature

    @staticmethod
    def fromBytes(bytes: bytearray) -> 'Event':

        temperature = Temperature.fromByte(bytes[0])
        hour = bytes[1] // 6
        minute = bytes[1] % 6 * 10
        return Event(temperature=temperature, hour=hour, minute=minute)

    def toBytes(self) -> bytearray:

        return bytearray([self.temperature.toByte(), self.hour * 6 + self.minute // 10])

    def to_dict(self) -> dict:

        return {
            "temparature": self.temperature.to_dict(),
            "until": f"{self.hour:02}:{self.minute:02}"
        }

    def __str__(self):

        return f"Event(temperature={str(self.temperature)}, until={self.hour:02}:{self.minute:02})"


class Program():

    DAY_SATURDAY = 0x00
    DAY_SUNDAY = 0x01
    DAY_MONDAY = 0x02
    DAY_TUESDAY = 0x03
    DAY_WEDNESDAY = 0x04
    DAY_THURSDAY = 0x05
    DAY_FRIDAY = 0x06
    DAY_WEEKEND = 0x07
    DAY_WORKDAY = 0x08
    DAY_EVERYDAY = 0x09
    DAY_TODAY = 0x0A
    DAY_TOMORROW = 0x0B

    DAYS = ["sat", "sun", "mon", "tue", "wed", "thu", "fri",
            "weekend", "work", "everyday", "today", "tomorrow"]

    DAYS_LONG = ["Saturday", "Sunday", "Monday",
                 "Tuesday", "Wednesday", "Thursday", "Friday"]

    def __init__(self, events: 'list[Event]' = list()):

        self.events: 'list[Event]' = events

    @staticmethod
    def fromBytes(bytes: bytearray) -> 'Program':

        events = list()
        for i in range(7):
            events.append(Event.fromBytes(bytes[i * 2: i * 2 + 2]))

        return Program(events=events)

    def toBytes(self) -> bytearray:

        bytes = list()
        for e in self.events:
            bytes.extend(e.toBytes())

        if len(bytes) < 14:
            bytes.extend([0] * (14 - len(bytes)))

        return bytearray(bytes)

    def to_dict(self) -> dict:

        return [e.to_dict() for e in self.events if e.hour != 0]

    def __str__(self):

        return "Program(%s)" % (", ".join([str(e) for e in self.events if e.hour != 0]))


class Vacation():

    def __init__(self, until: datetime = None):

        self.until: datetime = (
            until - timedelta(minutes=until.minute % 30)) if until else None

    @staticmethod
    def fromBytes(bytes: bytearray) -> 'Vacation':

        v = Vacation()
        if bytes[0] > 0:
            v.until = datetime(day=bytes[0], month=bytes[3], year=2000 +
                               bytes[1], hour=bytes[2] // 2, minute=bytes[2] % 2 * 30)
        return v

    def toBytes(self) -> bytearray:

        return bytearray([self.until.day, self.until.year - 2000, self.until.hour * 2 + self.until.minute // 30, self.until.month])

    def to_dict(self) -> dict:

        return {
            "until": (self.until.strftime("%Y-%m-%d %H:%M") if self.until else None)
        }

    def __str__(self):

        return "Vacation(until=%s)" % (self.until.strftime("%Y-%m-%d %H:%M") if self.until else "off")


class OpenWindowConfig():

    def __init__(self, temperature: Temperature = None, minutes: int = 0):

        self.minutes: int = minutes
        self.temperature: Temperature = temperature

    @staticmethod
    def fromBytes(bytes: bytearray) -> 'OpenWindowConfig':

        w = OpenWindowConfig()
        w.temperature = Temperature.fromByte(bytes[0])
        w.minutes = bytes[1] * 5
        return w

    def toBytes(self) -> bytearray:

        return bytearray([self.temperature.toByte(), self.minutes // 5])

    def to_dict(self) -> dict:

        return {
            "temperature": self.temperature.to_dict(),
            "minutes": self.minutes
        }

    def __str__(self):

        return f"OpenWindowConfig(minutes={self.minutes}, temperature={str(self.temperature)})"


class Mode():

    AUTO = 0x00
    MANUAL = 0x01
    VACATION = 0x02
    BOOST = 0x04
    DAYLIGHT_SUMMER_TIME = 0x08
    OPEN_WINDOW = 0x10
    LOCKED = 0x20
    UNKNOWN = 0x40
    BATTERY_LOW = 0x80

    MODES = ["AUTO", "MANUAL", "VACATION", "BOOST", "DAYLIGHT_SUMMER_TIME",
             "OPEN_WINDOW", "LOCKED", "UNKNOWN", "BATTERY_LOW"]

    def __init__(self, mode: int):

        self.mode = mode

    def to_dict(self) -> dict:

        modes = [Mode.MODES[0]
                 ] if self.mode & Mode.MANUAL != Mode.MANUAL else list()
        modes.extend([m for i, m in enumerate(
            Mode.MODES[1:]) if self.mode & 2**i == 2**i])
        return modes

    def __str__(self):

        return "Mode(modes=[%s])" % (",".join(self.to_dict()))


class Listener():

    def onScanSeen(self, device: BLEDevice) -> None:

        pass

    def onScanFound(self, device: BLEDevice) -> None:

        pass

    def onConnected(self, device: BLEDevice) -> None:

        pass

    def onDisconnected(self, device: BLEDevice) -> None:

        pass

    def onRequest(self, device: BLEDevice) -> None:

        pass

    def onNotify(self, device: BLEDevice, bytes: bytearray) -> None:

        pass


class Thermostat(BleakClient, Listener):

    MAC_PREFIX = "00:1A:22:"
    WAIT_NOTIFICATION = .2

    CHARACTERISTIC_DEVICE_NAME_STRING = "00002a24-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_VENDOR_STRING = "00002a29-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_REQUEST_HANDLE = "3fa4585a-ce4a-3bad-db4b-b8df8179ea09"
    CHARACTERISTIC_NOTIFICATION_HANDLE = "d0e8434d-cd29-0996-af41-6c90f4e0eb2a"

    COMMAND_SERIAL = [0x00]
    COMMAND_STATUS = [0x03]
    COMMAND_VACATION = [0x40]
    COMMAND_MODE_AUTO = [0x40, 0x00]
    COMMAND_MODE_MANUAL = [0x40, 0x40]

    COMMAND_SET_PROGRAM = [0x10]
    COMMAND_REQUEST_PROGRAM = [0x20]

    COMMAND_TEMPERATURE = [0x41]
    COMMAND_TEMPERATURE_ON = [0x41, 0x3c]
    COMMAND_TEMPERATURE_OFF = [0x41, 0x09]
    COMMAND_TEMPERATURE_COMFORT = [0x43]
    COMMAND_TEMPERATURE_ECO = [0x44]
    COMMAND_BOOST_START = [0x45, 0xff]
    COMMAND_BOOST_STOP = [0x45, 0x00]
    COMMAND_LOCK_ON = [0x80, 0x01]
    COMMAND_LOCK_OFF = [0x80, 0x00]
    COMMAND_COMFORT_ECO = [0x11]
    COMMAND_OFFSET = [0x13]
    COMMAND_OPEN_WINDOW = [0x14]
    COMMAND_RESET = [0xf0]

    NOTIFY_SERIAL = bytearray([0x01])
    NOTIFY_STATUS = bytearray([0x02, 0x01])
    NOTIFY_PROGRAM_CONFIRM = bytearray([0x02, 0x02])
    NOTIFY_PROGRAM_REQUEST = bytearray([0x21])

    def __init__(self, address: str) -> None:

        super().__init__(address, timeout=30.0)

        self.name: str = None
        self.vendor: str = None
        self.serialNumber: str = None
        self.mode: Mode = None
        self.temperature: Temperature = None
        self.valve: int = None
        self.vacation: Vacation = None
        self.programs: 'list[Program]' = [None] * 7
        self.ecoTemperature: Temperature = None
        self.comfortTemperature: Temperature = None
        self.openWindowConfig: OpenWindowConfig = None
        self.offsetTemperature: Temperature = None

    def onNotify(self, device, bytes):

        LOGGER.debug(f"<<< {device.address}: received notification("
                     f"{MyLogger.hexstr(bytes)})")

        if bytes.startswith(Thermostat.NOTIFY_SERIAL):

            self.serialNumber = bytearray(
                [b - 0x30 for b in bytes[4:-1]]).decode()
            LOGGER.info(f"{device.address}: received serialNo: "
                        f"{self.serialNumber}")

        elif bytes.startswith(Thermostat.NOTIFY_STATUS):

            self.mode = Mode(mode=bytes[2])
            self.valve = bytes[3]
            self.temperature = Temperature.fromByte(bytes[5])
            self.vacation = Vacation.fromBytes(bytes[6:10])
            self.openWindowConfig = OpenWindowConfig.fromBytes(bytes[10:12])
            self.comfortTemperature = Temperature.fromByte(bytes[12])
            self.ecoTemperature = Temperature.fromByte(bytes[13])
            self.offsetTemperature = Temperature.fromByte(bytes[14] - 7)
            LOGGER.info(f"{device.address}: received status: mode={str(self.mode)}, temperature={str(self.temperature)}, valve={str(self.valve)}%, vacation={str(self.vacation)}, openWindowConfig="
                        f"{str(self.openWindowConfig)}, comfortTemperature={str(self.comfortTemperature)}, ecoTemperature={str(self.ecoTemperature)}, offsetTemperature={str(self.offsetTemperature)}")

        elif bytes.startswith(Thermostat.NOTIFY_PROGRAM_REQUEST):

            day = bytes[1]
            program = Program.fromBytes(bytes=bytes[2:])
            self.programs[day] = program
            LOGGER.info(f"{device.address}: received program: "
                        f"{Program.DAYS[day]}={str(program)}")

        elif bytes.startswith(Thermostat.NOTIFY_PROGRAM_CONFIRM):

            LOGGER.info(f"{device.address}: program for "
                        f"{Program.DAYS[bytes[2]]} has been successful")

    async def read_gatt_char(self, characteristic) -> bytearray:

        LOGGER.debug(">>> %s: read_gatt_char(%s)" %
                     (self.address, characteristic))
        response = await super().read_gatt_char(characteristic)

        if response:
            LOGGER.debug("<<< %s: %s" %
                         (self.address, MyLogger.hexstr(response)))

        return response

    async def write_gatt_char(self, characteristic, data, response):

        LOGGER.debug(">>> %s: write_gatt_char(%s, %s)" %
                     (self.address, characteristic, MyLogger.hexstr(data)))
        response = await super().write_gatt_char(characteristic, data=data, response=response)

        if response:
            LOGGER.debug("<<< %s: %s" %
                         (self.address, MyLogger.hexstr(response)))

        return response

    async def connect(self):

        _self = self

        async def _notificationHandler(c, bytes: bytearray) -> None:

            _self.onNotify(device=_self, bytes=bytes)

        LOGGER.debug(f"{self.address}: connecting...")

        await super().connect()

        if self.is_connected:

            await self.start_notify(
                Thermostat.CHARACTERISTIC_NOTIFICATION_HANDLE, callback=_notificationHandler)
            LOGGER.info(f"{self.address}: successfully connected")

        else:

            raise EqivaException(f"{self.address}: Connection failed")

    async def disconnect(self):

        LOGGER.debug(f"{self.address}: disconnecting...")
        await super().disconnect()
        LOGGER.info(f"{self.address}: successfully disconnected")

    async def setTemperature(self, temperature: Temperature):

        LOGGER.info(f"{self.address}: set {str(temperature)}")
        bytes = list(Thermostat.COMMAND_TEMPERATURE)
        bytes.append(temperature.toByte())
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setTemperatureComfort(self):

        LOGGER.info(f"{self.address}: set mode to comfort")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_TEMPERATURE_COMFORT), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setTemperatureEco(self):

        LOGGER.info(f"{self.address}: set mode to ecor")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_TEMPERATURE_ECO), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setTemperatureOn(self):

        LOGGER.info(f"{self.address}: set thermostat on (30°C)")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_TEMPERATURE_ON), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setTemperatureOff(self):

        LOGGER.info(f"{self.address}: set thermostat off (4.5°C)")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_TEMPERATURE_OFF), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setModeAuto(self):

        LOGGER.info(f"{self.address}: set mode to auto")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_MODE_AUTO), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setModeManual(self):

        LOGGER.info(f"{self.address}: set mode to manual")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_MODE_MANUAL), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setBoost(self, on: bool):

        LOGGER.info(f"{self.address}: turn "
                    f"{'on' if on else 'off'} boost mode")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_BOOST_START if on else Thermostat.COMMAND_BOOST_STOP), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def requestStatus(self):

        LOGGER.info(f"{self.address}: sync time and request status")
        now = datetime.now()
        bytes = list(Thermostat.COMMAND_STATUS)
        bytes.extend([now.year % 100, now.month, now.day,
                     now.hour, now.minute, now.second])
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setVacation(self, temperature: Temperature, vacation: Vacation):

        LOGGER.info(f"{self.address}: set "
                    f"{str(vacation)} with {str(temperature)}")
        bytes = list(Thermostat.COMMAND_VACATION)
        bytes.append(temperature.toByte() + 0x80)
        bytes.extend(vacation.toBytes())

        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def requestProgram(self, day: int):

        LOGGER.info(f"{self.address}: request program for "
                    f"{str(Program.DAYS[day])}")

        requests = list()

        if day <= Program.DAY_FRIDAY:
            requests.append([Thermostat.COMMAND_REQUEST_PROGRAM[0], day])

        elif day == Program.DAY_WEEKEND:
            requests.extend([[Thermostat.COMMAND_REQUEST_PROGRAM[0], d]
                            for d in range(Program.DAY_SATURDAY, Program.DAY_SUNDAY + 1)])

        elif day == Program.DAY_WORKDAY:
            requests.extend([[Thermostat.COMMAND_REQUEST_PROGRAM[0], d]
                            for d in range(Program.DAY_MONDAY, Program.DAY_FRIDAY + 1)])

        elif day == Program.DAY_EVERYDAY:
            requests.extend([[Thermostat.COMMAND_REQUEST_PROGRAM[0], d]
                            for d in range(Program.DAY_SATURDAY, Program.DAY_FRIDAY + 1)])

        elif day == Program.DAY_TODAY:
            requests.append([Thermostat.COMMAND_REQUEST_PROGRAM[0],
                            (datetime.now().weekday() + 2) % 7])

        elif day == Program.DAY_TOMORROW:
            requests.append([Thermostat.COMMAND_REQUEST_PROGRAM[0],
                            (datetime.now().weekday() + 3) % 7])

        for r in requests:
            await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(r), response=True)

        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setProgram(self, day: int, program: Program) -> 'list[Thermostat]':

        LOGGER.info(f"{self.address}: set "
                    f"{str(program)} on {Program.DAYS[day]}")

        bytes = list(Thermostat.COMMAND_SET_PROGRAM)

        if day == Program.DAY_TODAY:
            day = (datetime.now().weekday() + 2) % 7
        elif day == Program.DAY_TOMORROW:
            day = (datetime.now().weekday() + 3) % 7
        bytes.append(day)

        bytes.extend(program.toBytes())

        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setOffsetTemperature(self, offset: Temperature):

        LOGGER.info(f"{self.address}: set offset {str(offset)}")
        bytes = list(Thermostat.COMMAND_OFFSET)
        bytes.append(offset.toByte() + 7)
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setComfortEcoTemperature(self, comfort: Temperature, eco: Temperature):

        LOGGER.info(f"{self.address}: set comfort to "
                    f"{str(comfort)} and eco to {str(eco)}")
        bytes = list(Thermostat.COMMAND_COMFORT_ECO)
        bytes.append(comfort.toByte())
        bytes.append(eco.toByte())
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setOpenWindow(self, openWindowConfig: OpenWindowConfig):

        LOGGER.info(f"{self.address}: set open window to "
                    f"{str(openWindowConfig)}")
        bytes = list(Thermostat.COMMAND_OPEN_WINDOW)
        bytes.extend(openWindowConfig.toBytes())
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(bytes), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def setLock(self, on: bool):

        LOGGER.info(f"{self.address}: turn {'on' if on else 'off'} lock")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_LOCK_ON if on else Thermostat.COMMAND_LOCK_OFF), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def reset(self):

        LOGGER.info(f"{self.address}: perform factory reset")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_RESET), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def requestSerialNo(self) -> None:

        LOGGER.info(f"{self.address}: request serialno")
        await self.write_gatt_char(Thermostat.CHARACTERISTIC_REQUEST_HANDLE, bytearray(Thermostat.COMMAND_SERIAL), response=True)
        await asyncio.sleep(Thermostat.WAIT_NOTIFICATION)

    async def requestName(self) -> str:

        LOGGER.info(f"{self.address}: request name")
        name = await self.read_gatt_char(Thermostat.CHARACTERISTIC_DEVICE_NAME_STRING)
        self.name = name.decode()
        LOGGER.info(f"{self.address}: name is {self.name}")
        return self.name

    async def requestVendor(self) -> str:

        LOGGER.info(f"{self.address}: request vendor")
        vendor = await self.read_gatt_char(Thermostat.CHARACTERISTIC_VENDOR_STRING)
        self.vendor = vendor.decode()
        LOGGER.info(f"{self.address}: name is {self.vendor}")
        return self.vendor

    def to_dict(self) -> dict:

        return {
            "mac": self.address,
            "name": self.name,
            "vendor": self.vendor,
            "serialNumber": self.serialNumber,
            "mode": self.mode.to_dict() if self.mode else None,
            "temperature": self.temperature.to_dict() if self.temperature else None,
            "valve": self.valve,
            "vacation": self.vacation.to_dict() if self.vacation else None,
            "program": {Program.DAYS[d]: p.to_dict() for d, p in enumerate(self.programs) if p},
            "ecoTemperature": self.ecoTemperature.to_dict() if self.ecoTemperature else None,
            "comfortTemperature": self.comfortTemperature.to_dict() if self.comfortTemperature else None,
            "openWindowConfig": self.openWindowConfig.to_dict() if self.openWindowConfig else None,
            "offsetTemperature": self.offsetTemperature.to_dict() if self.offsetTemperature else None
        }

    def __str__(self) -> str:

        programs = ", ".join(
            [f"{Program.DAYS[d]}={str(p)}" for d, p in enumerate(self.programs) if p])
        return f"Thermostat(address={self.address}, name={self.name}, vendor={self.vendor}, serialNo={self.serialNumber}, mode={str(self.mode)}, temperature={str(self.temperature)}, valve={str(self.valve)}%, vacation={str(self.vacation)}, programs=Programs({programs}), openWindowConfig={str(self.openWindowConfig)}, comfortTemperature={str(self.comfortTemperature)}, ecoTemperature={str(self.ecoTemperature)}, offsetTemperature={str(self.offsetTemperature)})"


class Alias():

    _KNOWN_DEVICES_FILE = ".known_eqivas"
    MAC_PATTERN = r"^([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2})$"

    def __init__(self) -> None:

        self.aliases: 'dict[str,str]' = dict()
        try:
            filename = os.path.join(os.environ['USERPROFILE'] if os.name == "nt" else os.environ['HOME']
                                    if "HOME" in os.environ else "~", Alias._KNOWN_DEVICES_FILE)

            if os.path.isfile(filename):
                with open(filename, "r") as ins:
                    for line in ins:
                        _m = re.match(
                            "([0-9A-Fa-f:]+) +(.*)$", line)
                        if _m and (_m.groups()[0].upper().startswith(Thermostat.MAC_PREFIX) or _m.groups()[0].upper().endswith(Thermostat.MAC_PREFIX)):
                            self.aliases[_m.groups()[0]] = _m.groups()[1]

        except:
            pass

    def resolve(self, label: str) -> 'set[str]':

        if re.match(Alias.MAC_PATTERN, label.upper()):
            label = label.upper()
            if label.upper().startswith(Thermostat.MAC_PREFIX) or label.upper().endswith(Thermostat.MAC_PREFIX):
                return [label]
            else:
                return None
        else:
            macs = {a.upper()
                    for a in self.aliases if label in self.aliases[a]}
            if macs:
                LOGGER.debug("Found mac-addresses for aliases: %s" %
                             ", ".join(macs))
            else:
                LOGGER.debug("No aliases found")

            return macs if macs else None

    def __str__(self) -> str:

        return "\n".join([f"{a}\t{self.aliases[a]}" for a in self.aliases])


class ThermostatController():

    def __init__(self, addresses: 'list[str]') -> None:

        self.addresses: 'list[str]' = addresses
        self.thermostats: 'list[Thermostat]' = list()

    async def connect(self, timeout) -> None:

        LOGGER.info("Request to connect to %s" % ", ".join(self.addresses))
        devices = await ThermostatController.scan(duration=timeout + len(self.addresses), filter_=self.addresses)
        LOGGER.debug("Found devices are %s" % (
            ", ".join([f"{d.name} ({d.address})" for d in devices]) if devices else "n/a"))

        if len(devices) < len(self.addresses):
            raise EqivaException(
                message="Could not find all given addresses")
        else:
            self.thermostats = [Thermostat(device) for device in devices]

        coros = [thermostat.connect() for thermostat in self.thermostats]
        await asyncio.gather(*coros)

    async def disconnect(self) -> None:

        coros = [thermostat.disconnect()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)

    async def setTemperature(self, temperature: Temperature) -> 'list[Thermostat]':

        coros = [thermostat.setTemperature(temperature=temperature)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setTemperatureComfort(self) -> 'list[Thermostat]':

        coros = [thermostat.setTemperatureComfort()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setTemperatureEco(self) -> 'list[Thermostat]':

        coros = [thermostat.setTemperatureEco()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setTemperatureOn(self) -> 'list[Thermostat]':

        coros = [thermostat.setTemperatureOn()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setTemperatureOff(self) -> 'list[Thermostat]':

        coros = [thermostat.setTemperatureOff()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setModeAuto(self) -> 'list[Thermostat]':

        coros = [thermostat.setModeAuto()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setModeManual(self) -> 'list[Thermostat]':

        coros = [thermostat.setModeManual()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setBoost(self, on: bool) -> 'list[Thermostat]':

        coros = [thermostat.setBoost(on=on)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def requestStatus(self) -> 'list[Thermostat]':

        coros = [thermostat.requestStatus()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setVacation(self, temperature: Temperature, datetime_: datetime = None, time_: timedelta = None, hours: int = 0) -> 'list[Thermostat]':

        if datetime_:
            vacation = Vacation(until=datetime_)
        elif time_:
            vacation = Vacation(until=datetime.now() + time_)
        else:
            vacation = Vacation(until=datetime.now() + timedelta(hours=hours))

        coros = [thermostat.setVacation(temperature=temperature, vacation=vacation)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def requestProgram(self, day: int) -> 'list[Thermostat]':

        coros = [thermostat.requestProgram(day=day)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setProgram(self, day: int, program: Program) -> 'list[Thermostat]':

        coros = [thermostat.setProgram(day=day, program=program)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setOffsetTemperature(self, offset: Temperature) -> 'list[Thermostat]':

        coros = [thermostat.setOffsetTemperature(offset=offset)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setComfortEcoTemperature(self, comfort: Temperature, eco: Temperature) -> 'list[Thermostat]':

        coros = [thermostat.setComfortEcoTemperature(comfort=comfort, eco=eco)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setOpenWindow(self, openWindowConfig: OpenWindowConfig) -> 'list[Thermostat]':

        coros = [thermostat.setOpenWindow(openWindowConfig=openWindowConfig)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def setLock(self, on: bool) -> 'list[Thermostat]':

        coros = [thermostat.setLock(on=on)
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def reset(self) -> None:

        coros = [thermostat.reset()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def requestSerialNo(self) -> 'list[Thermostat]':

        coros = [thermostat.requestSerialNo()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def requestName(self) -> 'list[Thermostat]':

        coros = [thermostat.requestName()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def requestVendor(self) -> 'list[Thermostat]':

        coros = [thermostat.requestVendor()
                 for thermostat in self.thermostats if thermostat.is_connected]
        await asyncio.gather(*coros)
        return self.thermostats

    async def requestDeviceInfo(self) -> 'list[Thermostat]':

        for thermostat in self.thermostats:
            await thermostat.requestName()
            await thermostat.requestVendor()
            await thermostat.requestSerialNo()
            await thermostat.requestStatus()
            await thermostat.requestProgram(Program.DAY_EVERYDAY)

        return self.thermostats

    def to_dict(self) -> dict:

        return [t.to_dict() for t in self.thermostats]

    @staticmethod
    async def scan(duration: int = 20, filter_: 'list[str]' = None, listener: Listener = None) -> 'set[BLEDevice]':

        found_devices: 'set[BLEDevice]' = set()
        found_bulbs: 'set[BLEDevice]' = set()
        if filter_:
            consumed_filter = [m for m in filter_]
        else:
            consumed_filter = None

        def callback(device: BLEDevice, advertising_data: AdvertisementData):

            if device not in found_devices and device.name:
                found_devices.add(device)
                if device.address.upper().startswith(Thermostat.MAC_PREFIX):

                    if consumed_filter and device.address not in found_bulbs:
                        if device.address in consumed_filter or device.name in consumed_filter:
                            found_bulbs.add(device)
                            consumed_filter.remove(
                                device.address if device.address in consumed_filter else device.name)
                            if listener:
                                listener.onScanFound(device)

                    elif not filter_:
                        found_bulbs.add(device)
                        if listener:
                            listener.onScanFound(device)

            if listener:
                listener.onScanSeen(device)

        async with BleakScanner(callback) as scanner:
            if consumed_filter:
                start_time = time.time()
                while consumed_filter and (start_time + duration) > time.time():
                    await asyncio.sleep(.1)
            elif duration:
                await asyncio.sleep(duration)
            else:
                while True:
                    await asyncio.sleep(1)

        return found_bulbs


class ThermostatCLI():

    _USAGE = "usage"
    _DESCR = "descr"
    _REGEX = "regex"
    _TYPES = "types"

    _COMMAND = "command"
    _ARGS = "args"
    _PARAMS = "params"

    COMMANDS = {
        "temp": {
            _USAGE: "--temp <temp>",
            _DESCR: "set temperature from 4.5 to 30.0°C in steps of 0.5°C or one of 'comfort', 'eco', 'off', 'on'",
            _REGEX: r"^(on|off|comfort|eco|4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0)$",
            _TYPES: [str]
        },
        "mode": {
            _USAGE: "--mode <auto|manual>",
            _DESCR: "set mode to auto or manual",
            _REGEX: r"^(auto|manual)$",
            _TYPES: [str]
        },
        "boost": {
            _USAGE: "--boost <on|off>",
            _DESCR: "start or stop boost",
            _REGEX: r"^(on|off)?$",
            _TYPES: [str]
        },
        "status": {
            _USAGE: "--status",
            _DESCR: "synchronize time and get status information",
            _REGEX: None,
            _TYPES: None
        },
        "vacation": {
            _USAGE: "--vacation <YYYY-MM-DD hh:mm|hh:mm|hh> <temp>",
            _DESCR: "set temperature for period, e.g. specific time, for hours and minutes from now on, for hours",
            _REGEX: r"^(20\d{2}\-\d{2}\-\d{2} (2[0-3]|[01]?[0-9]):[30]0|\d{1,2}:[0-5]\d|\d+) (4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0)$",
            _TYPES: [str] * 3
        },
        "program": {
            _USAGE: "--program [<day>] [<temp>] [<hh:mm> <temp>] ...",
            _DESCR: "request all programs, programs of a weekday OR set program with max. 7 events.\n<day> must be one of 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun', 'weekend', 'work', 'everyday', 'today', 'tomorrow'\ntime must be in stepts of 10 minutes",
            _REGEX: r"^(mon|tue|wed|thu|fri|sat|sun|weekend|work|everyday|today|tomorrow)?( (4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0)( [01]?\d| 2[0-3]):([0-5]0)){0,7}( (4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0))?$",
            _TYPES: [str] * 14
        },
        "offset": {
            _USAGE: "--offset <temp>",
            _DESCR: "set offset temperature from -3.5 to 3.5°C in steps of 0.5°C",
            _REGEX: r"^-?[0-3]\.[05]$",
            _TYPES: [float]
        },
        "comforteco": {
            _USAGE: "--comforteco <temp> <temp>",
            _DESCR: "set comfort and eco temperature from 4.5 to 30.0°C in steps of 0.5°C",
            _REGEX: r"^(4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0) (4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0)$",
            _TYPES: [float] * 2
        },
        "openwindow": {
            _USAGE: "--openwindow <temp> <minutes>",
            _DESCR: "set temperature (4.5 to 30.0) and minutes (in steps of 5min, max. 995min) after open windows has been detected",
            _REGEX: r"^(4\.5|[5-9]\.[05]|[12][0-9]\.[05]|30\.0) (\d{0,2}[05])$",
            _TYPES: [float, int]
        },
        "lock": {
            _USAGE: "--lock <on|off>",
            _DESCR: "lock or unlock thermostat",
            _REGEX: r"^(on|off)?$",
            _TYPES: [str]
        },
        "scan": {
            _USAGE: "--scan",
            _DESCR: "scan for Eqiva Smart Radiotor Thermostats",
            _REGEX: None,
            _TYPES: None
        },
        "aliases": {
            _USAGE: "--aliases",
            _DESCR: "print known aliases from .known_eqivas file",
            _REGEX: None,
            _TYPES: None
        },
        "reset": {
            _USAGE: "--reset",
            _DESCR: "perform factory reset",
            _REGEX: None,
            _TYPES: None
        },
        "serial": {
            _USAGE: "--serial",
            _DESCR: "request serialNo of thermostat",
            _REGEX: None,
            _TYPES: None
        },
        "name": {
            _USAGE: "--name",
            _DESCR: "request device name of thermostat",
            _REGEX: None,
            _TYPES: None
        },
        "vendor": {
            _USAGE: "--vendor",
            _DESCR: "request vendor of thermostat",
            _REGEX: None,
            _TYPES: None
        },
        "dump": {
            _USAGE: "--dump",
            _DESCR: "request full state of thermostat",
            _REGEX: None,
            _TYPES: None
        },
        "print": {
            _USAGE: "--print",
            _DESCR: "prints collected data of thermostat",
            _REGEX: None,
            _TYPES: None
        },
        "commands": {
            _USAGE: "--commands",
            _DESCR: "prints collected data of thermostat in command style for easy re-use",
            _REGEX: None,
            _TYPES: None
        },
        "json": {
            _USAGE: "--json",
            _DESCR: "prints information in json format",
            _REGEX: None,
            _TYPES: None
        },
        "log": {
            _USAGE: "--log <DEBUG|INFO|WARN|ERROR>",
            _DESCR: "set loglevel",
            _REGEX: r"^(DEBUG|INFO|WARN|ERROR)$",
            _TYPES: [str]
        },
        "help": {
            _USAGE: "--help [<command>]",
            _DESCR: "prints help optionally for given command",
            _REGEX: r"^([a-z-]+)?$",
            _TYPES: None
        }
    }

    def __init__(self, argv: 'list[str]') -> None:

        self.alias: Alias = Alias()
        try:

            argv.pop(0)
            if "--log" in sys.argv:
                LOGGER.level = MyLogger.LEVELS[sys.argv[sys.argv.index(
                    "--log") + 1]]

            if argv and (argv[0] == "--help" or argv[0] == "-h"):
                if len(argv) == 2:
                    print(self._build_help(
                        command=argv[1], header=True), file=sys.stderr, flush=True)
                else:
                    self.print_help()

            elif argv and argv[0] == "--scan":
                self.scan()

            elif argv and argv[0] == "--aliases":
                print(str(self.alias), flush=True)

            else:
                addresses, commands = self.parse_args(sys.argv)
                if addresses and len(addresses) > _MAX_BLE_CONNECTIONS:
                    raise EqivaException(message="Too many simultaneous connections requested, i.e. max. %i but requested %i" % (
                        _MAX_BLE_CONNECTIONS, len(addresses)))
                elif addresses and commands:
                    asyncio.run(self.process(
                        addresses=addresses, commands=commands))
                elif not addresses:
                    raise EqivaException(
                        message="Mac address or alias unknown")

        except EqivaException as e:
            LOGGER.error(e.message)

        except TimeoutError:
            LOGGER.error(
                f"TimeoutError! Maybe too many connections simultaneously?")

        except KeyboardInterrupt:
            pass

    def _build_help(self, command=None, header=False, msg="") -> None:

        s = ""

        if header == True:
            s = """Eqiva Smart Radiator Thermostat command line interface for Linux / Raspberry Pi / Windows

USAGE:   eqiva.py <mac_1/alias_1> [<mac_2/alias_2>] ... --<command_1> [<param_1> <param_2> ... --<command_2> ...]
         <mac_N>   : bluetooth mac address of thermostat
         <alias_N> : you can use aliases instead of mac address if there is a ~/.known_eqiva file
         <command> : a list of commands and parameters
         """

        if msg != "":
            s += "\n " + msg

        if command is not None and command in ThermostatCLI.COMMANDS:
            s += "\n " + \
                ThermostatCLI.COMMANDS[command][ThermostatCLI._USAGE].ljust(32)
            for i, d in enumerate(ThermostatCLI.COMMANDS[command][ThermostatCLI._DESCR].split("\n")):
                s += ("\n " + (" " * 32) + d if i > 0 or len(ThermostatCLI.COMMANDS[command]
                                                             [ThermostatCLI._USAGE]) >= 32 else d)

        if msg != "":
            s += "\n"

        return s

    def scan(self):

        class ScanListener(Listener):

            def __init__(self) -> None:
                self._seen: 'set[BLEDevice]' = set()

            def onScanSeen(self, device: BLEDevice) -> None:
                self._seen.add(device)
                print(' %i bluetooth devices seen' %
                      len(self._seen), end='\r', file=sys.stderr, flush=True)

            def onScanFound(self, device: BLEDevice) -> None:
                print(f"{device.address}     {device.name}", flush=True)

        print("MAC-Address           Thermostat name", flush=True)
        asyncio.run(ThermostatController.scan(listener=ScanListener()))

    def print_help(self):

        help = self._build_help(header=True)

        help += "\nBasic commands:"
        help += self._build_help(command="temp")
        help += self._build_help(command="mode")
        help += self._build_help(command="boost")
        help += self._build_help(command="vacation")
        help += self._build_help(command="status")

        help += "\n\nConfiguration commands:"
        help += self._build_help(command="program")
        help += self._build_help(command="offset")
        help += self._build_help(command="comforteco")
        help += self._build_help(command="openwindow")
        help += self._build_help(command="lock")

        help += "\n\nSetup commands:"
        help += self._build_help(command="scan")
        help += self._build_help(command="aliases")
        help += self._build_help(command="reset")

        help += "\n\nOther commands:"
        help += self._build_help(command="serial")
        help += self._build_help(command="name")
        help += self._build_help(command="vendor")
        help += self._build_help(command="dump")
        help += self._build_help(command="print")
        help += self._build_help(command="commands")
        help += self._build_help(command="json")
        help += self._build_help(command="log")
        help += self._build_help(command="help")

        help += "\n"
        print(help, file=sys.stderr, flush=True)

    def to_human_readable(self, controller: ThermostatController, command_style: bool = False) -> str:

        def mode_to_human_readable(mode: Mode) -> str:

            modes = mode.to_dict()
            if command_style:
                s = list()
                if Mode.MODES[0] in modes:
                    s.append(" --mode auto")
                elif Mode.MODES[1] in modes:
                    s.append(" --mode manual")
                s.append(" --boost %s" % ("on" if Mode.MODES[3] in modes else "off"))
                s.append(" --lock %s" % ("on" if Mode.MODES[6] in modes else "off"))
                return "\n".join(s)
            else:
                return ", ".join([m.lower().replace("_", " ") for m in modes])

        def temp_to_human_readable(temp: Temperature) -> str:

            if command_style:
                return f"{temp.valueC:.1f}"

            else:
                return f"{temp.valueC:.1f}°C ({temp.fahrenheit():.1f}°F)"

        def vacation_to_human_readable(vacation: Vacation, temperature: Temperature) -> str:

            if vacation.until:
                if command_style:
                    return "%s %s" % (vacation.until.strftime("%Y-%m-%d %H:%M"), temp_to_human_readable(temperature))
                else:
                    return "%s until %s" % (temp_to_human_readable(temperature), vacation.until.strftime("%Y-%m-%d %H:%M"))
            else:
                return "" if command_style else "off"

        def openwindow_to_human_readable(openwindowconfig: OpenWindowConfig) -> str:

            if command_style:
                return f"{temp_to_human_readable(openwindowconfig.temperature)} {openwindowconfig.minutes}"
            else:
                return f"{temp_to_human_readable(openwindowconfig.temperature)} for {openwindowconfig.minutes} minutes"

        def event_to_human_readable(event: Event) -> str:

            if command_style and event.hour == 24:
                return f"{temp_to_human_readable(event.temperature)}"
            else:
                return f"{temp_to_human_readable(event.temperature)} {event.hour:02}:{event.minute:02}"

        def program_to_human_readable(program: Program) -> str:

            if command_style:
                return " ".join([event_to_human_readable(event=e) for e in program.events if e.hour != 0])
            else:
                return "\n".join(["    %s" % event_to_human_readable(event=e) for e in program.events if e.hour != 0])

        def thermostat_to_human_readable(thermostat: Thermostat) -> str:

            s = list()
            s.append("")
            s.append("Thermostat %s" % thermostat.address)
            if thermostat.name and not command_style:
                s.append("  Name:                %s" % thermostat.name)

            if thermostat.vendor and not command_style:
                s.append("  Vendor:              %s" % thermostat.vendor)

            if thermostat.serialNumber and not command_style:
                s.append("  Serial no.:          %s" % thermostat.serialNumber)

            if thermostat.mode and not command_style:
                s.append("  Modes:               %s" %
                         mode_to_human_readable(thermostat.mode))
                s.append("  Temparature:         %s" %
                         temp_to_human_readable(thermostat.temperature))
                s.append("  Vacation:            %s" % vacation_to_human_readable(
                    thermostat.vacation, temperature=thermostat.temperature))
                s.append("  Valve:               %s" %
                         (f"{thermostat.valve}%"))
                s.append("")
                s.append("  Comfort temperature: %s" %
                         temp_to_human_readable(thermostat.comfortTemperature))
                s.append("  Eco temperature:     %s" %
                         temp_to_human_readable(thermostat.ecoTemperature))
                s.append("  Open window mode:    %s" %
                         openwindow_to_human_readable(thermostat.openWindowConfig))
                s.append("  Offset temperature:  %s" %
                         temp_to_human_readable(thermostat.offsetTemperature))
                s.append("")
            elif thermostat.mode:
                s.append(mode_to_human_readable(thermostat.mode))
                s.append(" --temp %s" %
                         temp_to_human_readable(thermostat.temperature))
                if thermostat.vacation.until:
                    s.append(" --vacation %s" % vacation_to_human_readable(
                        thermostat.vacation, temperature=thermostat.temperature))
                s.append(" --comforteco %s %s" % (
                    temp_to_human_readable(thermostat.comfortTemperature),
                    temp_to_human_readable(thermostat.ecoTemperature)))
                s.append(" --openwindow %s" %
                         openwindow_to_human_readable(thermostat.openWindowConfig))
                s.append(" --offset %s" %
                         temp_to_human_readable(thermostat.offsetTemperature))

            if command_style:
                s.extend([" --program %s %s" % (Program.DAYS[(d + 2) % 7], program_to_human_readable(thermostat.programs[(d + 2) %
                                                                                                                         7])) for d in range(7) if thermostat.programs[(d + 2) % 7]])
            else:
                s.extend(["  Program on %s:\n%s\n" % (Program.DAYS_LONG[(d + 2) % 7], program_to_human_readable(thermostat.programs[(d + 2) %
                                                                                                                                    7])) for d in range(7) if thermostat.programs[(d + 2) % 7]])

            return "\n".join(s)

        return "\n\n".join([thermostat_to_human_readable(thermostat=t) for t in controller.thermostats])

    async def process(self, addresses: 'list[str]', commands: 'list[dict]') -> None:

        try:
            controller = ThermostatController(addresses=addresses)

            await controller.connect(timeout=15)

            for command in commands:
                if command[ThermostatCLI._COMMAND] == "temp":

                    if command[ThermostatCLI._PARAMS][0] == "comfort":
                        await asyncio.gather(controller.setTemperatureComfort())

                    elif command[ThermostatCLI._PARAMS][0] == "eco":
                        await asyncio.gather(controller.setTemperatureEco())

                    elif command[ThermostatCLI._PARAMS][0] == "on":
                        await asyncio.gather(controller.setTemperatureOn())

                    elif command[ThermostatCLI._PARAMS][0] == "off":
                        await asyncio.gather(controller.setTemperatureOff())

                    else:
                        await asyncio.gather(controller.setTemperature(temperature=Temperature(valueC=float(command[ThermostatCLI._PARAMS][0]))))

                elif command[ThermostatCLI._COMMAND] == "mode":

                    if command[ThermostatCLI._PARAMS][0] == "auto":
                        await asyncio.gather(controller.setModeAuto())

                    elif command[ThermostatCLI._PARAMS][0] == "manual":
                        await asyncio.gather(controller.setModeManual())

                elif command[ThermostatCLI._COMMAND] == "boost":

                    if not command[ThermostatCLI._PARAMS] or command[ThermostatCLI._PARAMS][0] == "on":
                        await asyncio.gather(controller.setBoost(on=True))

                    elif command[ThermostatCLI._PARAMS][0] == "off":
                        await asyncio.gather(controller.setBoost(on=False))

                elif command[ThermostatCLI._COMMAND] == "status":
                    await asyncio.gather(controller.requestStatus())

                elif command[ThermostatCLI._COMMAND] == "vacation":
                    if len(command[ThermostatCLI._PARAMS]) == 3:
                        temp = Temperature(valueC=float(
                            command[ThermostatCLI._PARAMS][2]))
                        datetime_ = datetime.strptime(
                            " ".join(command[ThermostatCLI._PARAMS][:2]), "%Y-%m-%d %H:%M")
                        await asyncio.gather(controller.setVacation(temperature=temp, datetime_=datetime_))

                    elif len(command[ThermostatCLI._PARAMS]) == 2:

                        if ":" in command[ThermostatCLI._PARAMS][0]:
                            temp = Temperature(valueC=float(
                                command[ThermostatCLI._PARAMS][1]))
                            hhmm = command[ThermostatCLI._PARAMS][0].split(":")
                            await asyncio.gather(
                                controller.setVacation(
                                    temperature=temp,
                                    time_=timedelta(hours=int(hhmm[0]), minutes=int(hhmm[1]))))

                        else:
                            temp = Temperature(valueC=float(
                                command[ThermostatCLI._PARAMS][1]))
                            hours = int(command[ThermostatCLI._PARAMS][0])
                            await asyncio.gather(
                                controller.setVacation(
                                    temperature=temp,
                                    hours=hours))

                elif command[ThermostatCLI._COMMAND] == "program":

                    if len(command[ThermostatCLI._PARAMS]) == 0:

                        await asyncio.gather(controller.requestProgram(day=Program.DAY_EVERYDAY))

                    elif len(command[ThermostatCLI._PARAMS]) == 1:

                        await asyncio.gather(controller.requestProgram(day=Program.DAYS.index(command[ThermostatCLI._PARAMS][0])))

                    else:
                        events: 'list[Event]' = list()
                        temp = None
                        for i, param in enumerate(command[ThermostatCLI._PARAMS][1:]):
                            if i % 2:
                                hour, minute = tuple(param.split(":"))
                                events.append(
                                    Event(temperature=temp, hour=int(hour), minute=int(minute)))
                            else:
                                temp = Temperature(valueC=float(param))

                        events.append(
                            Event(temperature=events[0].temperature if i % 2 else temp, hour=24, minute=0))

                        await asyncio.gather(controller.setProgram(day=Program.DAYS.index(command[ThermostatCLI._PARAMS][0]), program=Program(events=events)))

                elif command[ThermostatCLI._COMMAND] == "offset":

                    await asyncio.gather(controller.setOffsetTemperature(offset=Temperature(valueC=command[ThermostatCLI._PARAMS][0])))

                elif command[ThermostatCLI._COMMAND] == "comforteco":

                    await asyncio.gather(controller.setComfortEcoTemperature(comfort=Temperature(valueC=command[ThermostatCLI._PARAMS][0]), eco=Temperature(valueC=command[ThermostatCLI._PARAMS][1])))

                elif command[ThermostatCLI._COMMAND] == "openwindow":

                    openWindowConfig = OpenWindowConfig(temperature=Temperature(
                        valueC=command[ThermostatCLI._PARAMS][0]), minutes=command[ThermostatCLI._PARAMS][1])
                    await asyncio.gather(controller.setOpenWindow(openWindowConfig=openWindowConfig))

                elif command[ThermostatCLI._COMMAND] == "lock":

                    if not command[ThermostatCLI._PARAMS] or command[ThermostatCLI._PARAMS][0] == "on":
                        await asyncio.gather(controller.setLock(on=True))

                    elif command[ThermostatCLI._PARAMS][0] == "off":
                        await asyncio.gather(controller.setLock(on=False))

                elif command[ThermostatCLI._COMMAND] == "reset":

                    await asyncio.gather(controller.reset())

                elif command[ThermostatCLI._COMMAND] == "serial":
                    await asyncio.gather(controller.requestSerialNo())

                elif command[ThermostatCLI._COMMAND] == "name":
                    await asyncio.gather(controller.requestName())

                elif command[ThermostatCLI._COMMAND] == "vendor":
                    await asyncio.gather(controller.requestVendor())

                elif command[ThermostatCLI._COMMAND] == "dump":
                    await asyncio.gather(controller.requestDeviceInfo())

                elif command[ThermostatCLI._COMMAND] == "print":
                    print(self.to_human_readable(
                        controller=controller), flush=True)

                elif command[ThermostatCLI._COMMAND] == "commands":
                    print(self.to_human_readable(
                        controller=controller, command_style=True), flush=True)

                elif command[ThermostatCLI._COMMAND] == "json":
                    print(json.dumps(controller.to_dict(), indent=2), flush=True)

        except EqivaException as ex:
            LOGGER.error(ex.message)

        except BleakError as ex:
            LOGGER.error(str(ex))

        finally:
            if controller:
                await controller.disconnect()

    def transform_commands(self, commands: 'list[dict]'):

        errors: 'list[str]' = list()

        for command in commands:

            cmd = command[ThermostatCLI._COMMAND]
            if cmd not in ThermostatCLI.COMMANDS:
                errors.append("ERROR: Unknown command <%s>" % cmd)
                continue

            cmd_def = ThermostatCLI.COMMANDS[cmd]

            regex: str = cmd_def[ThermostatCLI._REGEX]
            if regex and not re.match(regex, " ".join(command[ThermostatCLI._ARGS])):
                errors.append(
                    self._build_help(cmd, False,
                                     "ERROR: Please check parameters of command\n")
                )
                continue

            if cmd_def[ThermostatCLI._TYPES]:
                params = []
                for i, arg in enumerate(command[ThermostatCLI._ARGS]):
                    params.append(cmd_def[ThermostatCLI._TYPES][i](arg))

                command["params"] = params

        if len(commands) == 0:
            errors.append(
                "No commands given. Use --help in order to get help")

        if len(errors) > 0:
            raise EqivaException("\n".join(errors))

        return commands

    def parse_args(self, argv: 'list[str]') -> 'tuple[set[str], list[dict]]':

        addresses: 'set[str]' = set()
        commands: 'list[tuple[str, list[str]]]' = list()

        cmd_group = False
        for arg in argv:

            is_cmd = arg.startswith("--")
            cmd_group |= is_cmd
            if not cmd_group:
                _addresses = self.alias.resolve(arg)
                if _addresses:
                    for a in _addresses:
                        addresses.add(a)
                else:
                    addresses.add(arg)

            elif is_cmd:
                commands.append({
                    "command": arg[2:],
                    "args": list()
                })

            else:
                commands[-1]["args"].append(arg)

        self.transform_commands(commands)

        return addresses, commands


if __name__ == '__main__':

    ThermostatCLI(argv=sys.argv)
