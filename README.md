# Eqiva-Smart-Radiator-Thermostat
Python script and lib in order to control Eqiva Smart Radiator Thermostat via Bluetooth LE with Raspberry Pi, any Linux distribution and MS Windows.

Full-featured CLI and API based on [bleak](https://github.com/hbldh/bleak) for Eqiva Smart Radiator Thermostat.

## Command line tool
```
$ ./eqiva.py --help
Eqiva Smart Radiator Thermostat command line interface for Linux / Raspberry Pi / Windows

USAGE:   eqiva.py <mac_1/alias_1> [<mac_2/alias_2>] ... --<command_1> [<param_1> <param_2> ... --<command_2> ...]
         <mac_N>   : bluetooth mac address of thermostat
         <alias_N> : you can use aliases instead of mac address if there is a ~/.known_eqivas file
         <command> : a list of commands and parameters

Basic commands:
 --temp <temp>                   set temperature from 4.5 to 30.0°C in steps of 0.5°C or one of 'comfort', 'eco', 'off', 'on'
 --mode <auto|manual>            set mode to auto or manual
 --boost <on|off>                start or stop boost
 --vacation <YYYY-MM-DD hh:mm|hh:mm|hh> <temp>
                                 set temperature for period, e.g. specific time, for hours and minutes from now on, for hours
 --status                        synchronize time and get status information

Configuration commands:
 --program [<day>] [<temp>] [<hh:mm> <temp>] ...
                                 request all programs, programs of a weekday OR set program with max. 7 events.
                                 <day> must be one of 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun', 'weekend', 'work', 'everyday', 'today', 'tomorrow'
                                 time must be in steps of 10 minutes
 --offset <temp>                 set offset temperature from -3.5 to 3.5°C in steps of 0.5°C
 --comforteco <temp> <temp>      set comfort and eco temperature from 4.5 to 30.0°C in steps of 0.5°C
 --openwindow <temp> <minutes>   set temperature (4.5 to 30.0) and minutes (in steps of 5min, max. 995min) after open windows has been detected
 --lock <on|off>                 lock or unlock thermostat

Setup commands:
 --scan                          scan for Eqiva Smart Radiator Thermostats
 --aliases                       print known aliases from .known_eqivas file
 --reset                         perform factory reset

Other commands:
 --serial                        request serialNo of thermostat
 --name                          request device name of thermostat
 --vendor                        request vendor of thermostat
 --dump                          request full state of thermostat
 --print                         prints collected data of thermostat
 --commands                      prints collected data of thermostat in command style for easy re-use
 --json                          prints information in json format
 --log <DEBUG|INFO|WARN|ERROR>   set loglevel
 --help [<command>]              prints help optionally for given command
```

## Preparation / Preconditions
The CLI / API is written in Python 3. It utilizes the Python module [bleak](https://github.com/hbldh/bleak) which can be installed as follows:

```
$ pip3 install bleak==1.0.1
```

Make sure that script is executable:
```
$ chmod +x eqiva.py
```

## Pairing
Pairing is not required if your thermostat asks for a 4-digit pin. However, after inserting the battery, you must disable and re-enable Bluetooth in the menu. Otherwise the device is not found via Bluetooth. After that you can immediately control it via BT.

Thermostats with newer firmware, e.g. 1.46 and above, ask for a 6-digit pin and pairing is required. This works for me:

* Step 1: open ```bluetoothctl```
* Step 2: select bluetooth device (required in my setup since I have two controllers, i.e. a built-in one and an external USB dongle)
* Step 3: connect to thermostat by entering mac address
* Step 4: enter passkey
* Step 5: disconnect and quit.

The thermostat must be in pairing mode as well. The displayed 6 digit code must be used for pairing.

Note: It seems that the same thermostat can be paired to multiple clients, e.g. your smartphone, PCs etc.

Example:
```
$ bluetoothctl
Agent registered
[CHG] Controller 00:1A:7D:DA:71:13 Pairable: yes
[CHG] Controller 14:F6:D8:D4:1F:F1 Pairable: yes
[bluetooth]# select  00:1A:7D:DA:71:13
Controller 00:1A:7D:DA:71:13 my-pc [default]
[bluetooth]# connect 00:1A:22:0A:91:CF
Attempting to connect to 00:1A:22:0A:91:CF
[CHG] Device 00:1A:22:0A:91:CF Connected: yes
[CHG] Device 00:1A:22:0A:91:CF Connected: no
Connection successful
[CHG] Device 00:1A:22:0A:91:CF Connected: yes
Request passkey
[agent] Enter passkey (number in 0-999999): 308448
[NEW] Primary Service (Handle 0x8281)
        /org/bluez/hci1/dev_00_1A_22_0A_91_CF/service0200
        00001801-0000-1000-8000-00805f9b34fb
        Generic Attribute Profile
...
[CC-RT-BLE]# disconnect
[CC-RT-BLE]# quit
```

Afterwards everything works again. Don't forget to explicitly disconnect when you are in ```bluetoothctl```. Otherwise, the script can't connect since the thermostat is occupied. Note that for some reason I had to repeat the pairing process after some time (in my case a month or so).

## Find thermostats and adding aliases
First of all, you should scan for Eqiva Thermostats. This can be done by calling the scan command:
```
$ ./eqiva.py --scan
MAC-Address           Thermostat name
00:1A:22:XX:XX:XX     CC-RT-BLE
00:1A:22:XX:XX:XX     CC-RT-BLE
00:1A:22:XX:XX:XX     CC-RT-BLE
```

You can call the script by using the MAC address:
```
$ ./eqiva.py 00:1A:22:XX:XX:XX --status --print

Thermostat 00:1A:22:XX:XX:XX
  Modes:               auto, vacation, daylight summer time
  Temperature:         18.5°C (65.3°F)
  Vacation:            until 2024-11-24 10:00
  Valve:               0%

  Eco temperature:     17.5°C (63.5°F)
  Comfort temperature: 20.5°C (68.9°F)
  Open window mode:    5.0°C (41.0°F) for 20 minutes
  Offset temperature:  0.0°C (32.0°F)
```

Since this isn't very handy it is recommended to create a file in your home directory called ```.known_eqivas```. This is my file:
```
$ cat ~/.known_eqivas
00:1A:22:XX:XX:XF Wohnzimmer
00:1A:22:XX:XX:X0 Küche
00:1A:22:XX:XX:XE Bad
```

This allows me to call the script by using an alias, e.g.
```
$ ./eqiva.py Wohnz --status --print
...
```

Note that I have just written ```Wohnz``` instead of the full name. The alias is like a pattern. Every line that matches in ```.known_eqivas``` will be connected. The format of the lines is the following:

```
11:22:33:44:55:66[SPACES]+Name # Optional comment
```


## Multiple devices and command queueing
Connections to multiple devices are supported although I recommend connecting just to a single device. In addition, you can send multiple commands by queueing these commands.

Example:
```
$ ./eqiva.py Wohnz --mode manual --temp 16.5 --status --print
```

This command connects to the device with alias 'Wohnz'. Then it sends four commands and prints gathered information:
1. Set thermostat to manual mode
2. Set temperature to 16.5°C
3. Request status
4. Print gathered information

## Basic commands
### Ask for help
Type the following to get help for all commands
```
$ ./eqiva.py --help
...
```

To get help for a specific command you can do it like this:
```
$ ./eqiva.py --help mode
Eqiva Smart Radiator Thermostat command line interface for Linux / Raspberry Pi / Windows

USAGE:   eqiva.py <mac_1/alias_1> [<mac_2/alias_2>] ... --<command_1> [<param_1> <param_2> ... --<command_2> ...]
         <mac_N>   : bluetooth mac address of thermostat
         <alias_N> : you can use aliases instead of mac address if there is a ~/.known_eqivas file
         <command> : a list of commands and parameters

 --mode <auto|manual>            set mode to auto or manual
```

### Print status and synchronize time
To print the status, you can use the ```--status``` command. It also synchronizes the time. Since it does not print the requested information, you must also use the ```--print``` command to print the result to the console.

```
$ ./eqiva.py Wohnz --status --print

Thermostat 00:1A:22:XX:XX:XX

  Modes:               manual, daylight summer time
  Temperature:         16.5°C (61.7°F)
  Vacation:            off
  Valve:               0%

  Eco temperature:     16.0°C (60.8°F)
  Comfort temperature: 19.5°C (67.1°F)
  Open window mode:    5.0°C (41.0°F) for 10 minutes
  Offset temperature:  0.0°C (32.0°F)

```

As you can see some information like name and serial no. aren't available yet. To get this information as well it must be queried explicitly by queuing commands.
```
$ ./eqiva.py Wohnz --status --vendor --name --serial --print

Thermostat 00:1A:22:XX:XX:XX
  Name:                CC-RT-BLE
  Vendor:              eq-3
  Serial no.:          OEQ06XXXXX
  Modes:               manual, daylight summer time
  Temperature:         16.5°C (61.7°F)
  Vacation:            off
  Valve:               0%

  Eco temperature:     16.0°C (60.8°F)
  Comfort temperature: 19.5°C (67.1°F)
  Open window mode:    5.0°C (41.0°F) for 10 minutes
  Offset temperature:  0.0°C (32.0°F)
```

### Set temperature
To set the target temperature do the following:

Set the temperature to 16.5°C:
```
$ ./eqiva.py Wohnz --temp 16.5
```

Set the temperature to the configured eco temperature:
```
$ ./eqiva.py Wohnz --temp eco
```

Set the temperature to the configured comfort temperature:
```
$ ./eqiva.py Wohnz --temp comfort
```

Turn the thermostat off (i.e. set temperature to 4.5°C)
```
$ ./eqiva.py Wohnz --temp off
```

Turn the thermostat on (i.e. set temperature to 30.0°C)
```
$ ./eqiva.py Wohnz --temp on
```

Note: The thermostat should be in auto mode. Otherwise, the target temperature will change when the next scheduled program event occurs.

### Set mode
Set the temperature to manual:
```
$ ./eqiva.py Wohnz --mode manual
```

Set the temperature to auto:
```
$ ./eqiva.py Wohnz --mode auto
```

### Boost mode
Start boost mode like this:
```
$ ./eqiva.py Wohnz --boost on
```

or only

```
$ ./eqiva.py Wohnz --boost
```

It runs for 5 minutes. If you want to stop boost mode, do the following:
```
$ ./eqiva.py Wohnz --boost off
```

### Vacation mode
You can set the temperature for a period of time by using the vacation mode. Programs will be ignored in this period and the thermostat is kind of locked.

If you want the vacation mode until a specific date, do it like this:
```
$ ./eqiva.py Wohnz --vacation 2024-12-31 23:30 16.5
```
This will set the temperature of 16.5°C until 2024-12-31 23:30. Note that the minutes part in time must be full hour or half an hour, i.e. ':00' or ':30'

If you want the vacation mode for the next two and a half hours starting from now to the following:
```
$ ./eqiva.py Wohnz --vacation 2:30 16.5
```

or even shorter by just using hours. This sets the temperature of 16.5°C for the next 2 hours.
```
$ ./eqiva.py Wohnz --vacation 2 16.5
```

## Configuration
### Programs
The thermostat supports setting different programs for each day of the week. Per day 7 different schedules are supported.

Type the following to set a program for a day:
```
$ ./eqiva.py Wohnz --program mon 17.5 07:00 20.5 21:00 17.5
```

Note: For easier program changes, you can query the current configuration and output it in command-style like this
```
$ ./eqiva.py Wohnz --program --commands

Thermostat 00:1A:22:0A:91:CF
  --program mon 17.5 07:00 20.5 21:00 17.5
  --program tue 17.5 07:00 20.5 21:00 17.5
  --program wed 17.5 17:00 20.5 21:00 17.5
  --program thu 17.5 07:00 20.5 21:00 17.5
  --program fri 17.5 07:00 20.5 22:00 17.5
  --program sat 17.5 08:00 20.5 22:00 17.5
  --program sun 17.5 08:00 20.5 21:00 17.5
```

### Offset temperature
To set the offset temperature, enter this:
```
$ ./eqiva.py Wohnz --offset 0.0
```

### Comfort and eco temperature
To set the comfort and eco temperatures, enter this:
```
$ ./eqiva.py Wohnz --comforteco 20.5 16.5
```

### Open window configuration
To configure the open-window mode, enter this:
```
$ ./eqiva.py Wohnz --openwindow 5.0 10
```
5.0 is the temperature which is set for 10 minutes after an open window has been detected.

### Lock / unlock
To lock the thermostat, enter this:
```
$ ./eqiva.py Wohnz --lock on
```

For unlocking it goes like this:
```
$ ./eqiva.py Wohnz --lock off
```

### Factory reset
To perform a factory reset enter the following:
```
$ ./eqiva.py Wohnz --reset
```

## Device information
### Name, vendor, serial
To request the name, vendor, and serial, enter the following:
```
$ ./eqiva.py Wohnz --name --vendor --serial --print

Thermostat 00:1A:22:XX:XX:XX
  Name:                CC-RT-BLE
  Vendor:              eq-3
  Serial no.:          OEQ06XXXXX
```

### Dump all information of your thermostat
If you want to get all information of your thermostat, you can use the ```--dump``` command.

```
$ ./eqiva.py Wohnz --dump --print

Thermostat 00:1A:22:XX:XX:XX
  Name:                CC-RT-BLE
  Vendor:              eq-3
  Serial no.:          OEQ06XXXXX
  Modes:               manual, daylight summer time
  Temperature:         20.0°C (68.0°F)
  Vacation:            off
  Valve:               77%

  Eco temperature:     16.0°C (60.8°F)
  Comfort temperature: 19.5°C (67.1°F)
  Open window mode:    5.0°C (41.0°F) for 10 minutes
  Offset temperature:  0.0°C (32.0°F)

  Program on Monday:
    17.5°C (63.5°F) until 07:00
    20.5°C (68.9°F) until 21:00
    17.5°C (63.5°F) until 24:00

  Program on Tuesday:
    17.5°C (63.5°F) until 07:00
    20.5°C (68.9°F) until 21:00
    17.5°C (63.5°F) until 24:00

  Program on Wednesday:
    17.5°C (63.5°F) until 17:00
    20.5°C (68.9°F) until 21:00
    17.5°C (63.5°F) until 24:00

  Program on Thursday:
    17.5°C (63.5°F) until 07:00
    20.5°C (68.9°F) until 21:00
    17.5°C (63.5°F) until 24:00

  Program on Friday:
    17.5°C (63.5°F) until 07:00
    20.5°C (68.9°F) until 22:00
    17.5°C (63.5°F) until 24:00

  Program on Saturday:
    17.5°C (63.5°F) until 08:00
    20.5°C (68.9°F) until 22:00
    17.5°C (63.5°F) until 24:00

  Program on Sunday:
    17.5°C (63.5°F) until 08:00
    20.5°C (68.9°F) until 21:00
    17.5°C (63.5°F) until 24:00
```

or in command format
```
$ ./eqiva.py Wohnz --dump --commands

Thermostat 00:1A:22:0A:91:CF
  --temp 16.5
  --mode auto
  --vacation 2024-12-31 23:30 16.5
  --comforteco 19.5 16.0
  --openwindow 5.0 10
  --offset 0.0
  --program mon 17.5 07:00 20.5 21:00 17.5
  --program tue 17.5 07:00 20.5 21:00 17.5
  --program wed 17.5 17:00 20.5 21:00 17.5
  --program thu 17.5 07:00 20.5 21:00 17.5
  --program fri 17.5 07:00 20.5 22:00 17.5
  --program sat 17.5 08:00 20.5 22:00 17.5
  --program sun 17.5 08:00 20.5 21:00 17.5
```

or in json format

```
$ ./eqiva.py Wohnz --dump --json
[
  {
    "name": "CC-RT-BLE",
    "vendor": "eq-3",
    "serialNumber": "OEQXXXXXXX",
    "mode": [
      "MANUAL",
      "DAYLIGHT_SUMMER_TIME"
    ],
    "temperature": {
      "valueC": 20.0,
      "valueF": 68.0
    },
    "valve": 64,
    "vacation": {
      "until": null
    },
    "program": {
      "sat": [
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "08:00"
        },
        {
          "temperature": {
            "valueC": 20.5,
            "valueF": 68.9
          },
          "until": "22:00"
        },
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "24:00"
        }
      ],
      "sun": [
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "08:00"
        },
        {
          "temperature": {
            "valueC": 20.5,
            "valueF": 68.9
          },
          "until": "21:00"
        },
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "24:00"
        }
      ],
      "mon": [
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "07:00"
        },
        {
          "temperature": {
            "valueC": 20.5,
            "valueF": 68.9
          },
          "until": "21:00"
        },
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "24:00"
        }
      ],
      "tue": [
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "07:00"
        },
        {
          "temperature": {
            "valueC": 20.5,
            "valueF": 68.9
          },
          "until": "21:00"
        },
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "24:00"
        }
      ],
      "wed": [
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "17:00"
        },
        {
          "temperature": {
            "valueC": 20.5,
            "valueF": 68.9
          },
          "until": "21:00"
        },
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "24:00"
        }
      ],
      "thu": [
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "07:00"
        },
        {
          "temperature": {
            "valueC": 20.5,
            "valueF": 68.9
          },
          "until": "21:00"
        },
        {
          "temperature": {
            "valueC": 17.5,
            "valueF": 63.5
          },
          "until": "24:00"
        }
      ]
    },
    "ecoTemperature": {
      "valueC": 16.0,
      "valueF": 60.8
    },
    "comfortTemperature": {
      "valueC": 19.5,
      "valueF": 67.1
    },
    "openWindowConfig": {
      "temperature": {
        "valueC": 5.0,
        "valueF": 41.0
      },
      "minutes": 10
    },
    "offsetTemperature": {
      "valueC": 0.0,
      "valueF": 32.0
    }
  }
]
```

## Python API
Take a look at [example.py](https://github.com/Heckie75/Eqiva-Smart-Radiator-Thermostat/blob/main/example.py) to find out how to use the API. 

## Eqiva-Smart-Radiator-Thermostat Bluetooth LE API
see [eq-3-radiator-thermostat-api.md](https://github.com/Heckie75/Eqiva-Smart-Radiator-Thermostat/blob/main/eq-3-radiator-thermostat-api.md)
