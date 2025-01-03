#!/usr/bin/python3
import asyncio
from datetime import datetime, timedelta

from eqiva import (EqivaException, Event, OpenWindowConfig, Program,
                   Temperature, Thermostat, Vacation)


async def do_stuff() -> None:

    thermostat = Thermostat('00:1A:22:0C:19:60')
    try:
        await thermostat.connect()

        # Meta information
        await thermostat.requestName()
        await thermostat.requestVendor()
        await thermostat.requestSerialNo()

        # request current status
        await thermostat.requestStatus()
        print(str(thermostat))

        # set modes
        await thermostat.setModeManual()
        # await thermostat.setModeAuto()
        # await thermostat.setBoost()

        # set temperature
        await thermostat.setTemperature(temperature=Temperature(valueC=20.5))
        # await thermostat.setTemperatureComfort()
        # await thermostat.setTemperatureEco()
        print(str(thermostat))

        # get programs
        await thermostat.requestProgram(day=Program.DAY_MONDAY)
        print(thermostat.programs[Program.DAY_MONDAY])

        # set programs
        events = [
            Event(temperature=Temperature(valueC=5.0), hour=6, minute=40),
            Event(temperature=Temperature(valueC=20.5), hour=7, minute=40),
            Event(temperature=Temperature(valueC=5.0), hour=24, minute=0)
        ]
        await thermostat.setProgram(day=Program.DAY_MONDAY, program=Program(events=events))

        # vacation mode
        await thermostat.setVacation(temperature=Temperature(valueC=5.0), vacation=Vacation(until=datetime.now() + timedelta(hours=1)))
        print(str(thermostat))

        # configuration
        await thermostat.setComfortEcoTemperature(comfort=Temperature(valueC=20.5), eco=Temperature(valueC=18.5))
        await thermostat.setOffsetTemperature(offset=Temperature(valueC=0.0))
        await thermostat.setOpenWindow(OpenWindowConfig(temperature=Temperature(valueC=5.0), minutes=30))

        # lock
        await thermostat.setLock(on=False)
        # await thermostat.setLock(on=True)
        print(str(thermostat))

    except EqivaException as ex:
        print(ex.message)

    if thermostat:
        await thermostat.disconnect()


if __name__ == '__main__':

    asyncio.run(do_stuff())
