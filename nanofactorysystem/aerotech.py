##########################################################################
# Copyright (c) 2022-2024 Reinhard Caspary                               #
# <reinhard.caspary@phoenixd.uni-hannover.de>                            #
# This program is free software under the terms of the MIT license.      #
##########################################################################

import os
import socket
import time
from scidatacontainer import Container

from . import sysConfig
from .attenuator import Attenuator
from .parameter import Parameter

# Task states
TASKSTATE_Unavailable = 0
TASKSTATE_Inactive = 1
TASKSTATE_Idle = 2
TASKSTATE_ProgramReady = 3
TASKSTATE_ProgramRunning = 4
TASKSTATE_ProgramFeedheld = 5
TASKSTATE_ProgramPaused = 6
TASKSTATE_ProgramComplete = 7
TASKSTATE_Error = 8
TASKSTATE_Queue = 9
TASKSTATE = ("unavailable", "inactive", "idle", "programReady",
             "programRunning", "programFeedheld", "programPaused",
             "programComplete", "error", "queue")

# Drive status bit masks
DRIVESTATUS_InPosition = 0x02000000

# AeroBasic program doing an aial line scan
ZLINE_PGM = """
DVAR $dz
DVAR $dzhalf
DVAR $fast
DVAR $slow

$fast = $global[0]
$slow = $global[1]
$dz = $global[2]
$dzhalf = -0.5 * $dz

LOOKAHEAD FAST
CRITICAL START
VELOCITY ON
RAMP MODE RATE
RAMP RATE 0.00000
WAIT MODE AUTO
INCREMENTAL

LINEAR Z $dzhalf F $fast
GALVO LASEROVERRIDE A ON
LINEAR Z $dz F $slow
GALVO LASEROVERRIDE A OFF
LINEAR Z $dzhalf F $fast

ABSOLUTE
VELOCITY ON
CRITICAL END
END PROGRAM
"""


##########################################################################
class A3200(Parameter):
    
    """ Class for controlling an Aerotech A3200 system."""
    
    _defaults = {
        "xInit": None,
        "yInit": None,
        "zInit": None,
        "zMax": None,
        "tasks": {},
        "systemDescription": "Multi-axis motion controller system",
        "model": "A3200",
        "manufacturer": "Aerotech",
        "softwareVersion": None,
        # ASCII command interface defined in the A3200 Configuration
        # Manager:
        # Computer - Open Files - * - System - Communication - ASCII
        # Note: You must reset the controller for changes to have an
        # effect
        "host": "127.0.0.1",
        "port": 8000,
        "cmdTerminatingChar": 10, # CommandTerminatingCharacter
        "cmdSuccessChar": 37,     # CommandSuccessCharacter
        "cmdInvalidChar": 33,     # CommandInvalidCharacter
        "cmdFaultChar": 35,       # CommandFaultCharacter
        }
        
    def __init__(self, user, logger=None, **kwargs):

        # Initialize parameter class
        args = kwargs.get("controller", {})        
        super().__init__(user, logger, **args)
        self.log.info("Initializing Aerotech A3200 system.")

        # Store controller data dictionary
        self.controller = sysConfig.controller

        # Safety net: maximum z position
        if self["zMax"] is None:
            raise RuntimeError("Maximum z position is missing!")

        # TCP socket to the A3200 system
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.opened = False

        # Connect to the A3200 system
        try:
            self.socket.connect((self["host"], self["port"]))
        except ConnectionRefusedError:
            self.log.error("Connection to A3200 controller failed!")
            return
        self.opened = True

        # Acknowledge all warnings
        self.reset()

        # Some standard definitions
        self.run("ABSOLUTE")
        self.run("METRIC")
        self.run("SECONDS")
        self.run("VELOCITY OFF")
        self.run("IFOV OFF")

        # Store software version
        self["softwareVersion"] = self.version()

        # Store current xyz position
        self["xInit"], self["yInit"], self["zInit"] = self.position("XYZ")

        # No program tasks loaded yet
        self.task_pgms = {}

        # Laser calibration
        args = kwargs.get("attenuator", {})        
        self.attenuator = Attenuator(user, self.log, *args)

        # Done
        self.log.info(str(self))
        self.log.info("Initialized Aerotech A3200 system.")


    def __str__(self):

        if self.opened:
            result = "%s %s (driver %s) at %s:%s." % \
                     (self["manufacturer"], self["model"],
                      self["softwareVersion"], self["host"], self["port"])
        else:
            result = "Aerotech A3200 disconnected."
        return result


    def close(self):

        """ Close connection to the A3200 system. """

        self.socket.close()
        self.opened = False


    def __enter__(self):

        """ Context manager entry method. """

        return self


    def __exit__(self, errtype, value, tb):

        """ Context manager exit method. """

        #print("".join(traceback.format_exception(errtype, value, tb)))
        self.close()


    def run(self, cmd):

        """ Run the given AeroBasic command on the A3200 controller. """

        if not self.opened:
            raise RuntimeError("Not connected!")

        # Append terminal character
        if cmd[-1] != chr(self["cmdTerminatingChar"]):
            cmd += chr(self["cmdTerminatingChar"])

        # Send command
        self.socket.send(cmd.encode())

        # Read and return response
        line = self.socket.recv(4096).decode().strip()
        code, response = line[0], line[1:]
        if code != chr(self["cmdSuccessChar"]):
            raise RuntimeError("Command failed!")
        return response


    def version(self):

        """ Return A3200 software version. """

        return self.run("~VERSION")

    
    def reset(self):

        """ Acknowledge all warnings. """

        if not self.opened:
            raise RuntimeError("Not connected!")

        self.run("ACKNOWLEDGEALL")
        

    def home(self, axes=None):
        
        """ Run a home cycle on the given axes. """

        if axes in None:
            axes = "XYZ"
        axes = self.normaxes(axes, "XYZ")
        for axis in axes:
            self.run("HOME %s" % axis)


    def normaxes(self, axes, limit=None):

        """ Return normalized string of uppercase axis letters. The
        parameter limit may contain a string of allowed axis letters.
        Default is "XYZAB". """

        if limit is None:
            limit = "XYZAB"
        else:
            limit = limit.upper()
        false = tuple(c for c in axes if c.upper() not in limit)
        if len(false) > 0:
            false = ", ".join(false)
            raise RuntimeError("Wrong axes: %s!" % false)
        return axes.upper()


    def moveinc(self, speed, **axes):

        """ Move on one or more axes with the given speed in micrometers
        per second. The relative movement distances are given in
        micrometers as named parameters. Example: moveinc(100, x=10.7,
        z=-2.0)"""

        dest = []
        for axis, pos in axes.items():
            axis = self.normaxes(axis, "XYZAB")
            if axis == "Z":
                self.z += pos
                if self.z > self["zMax"]:
                    self.close()
                    raise RuntimeError("Maximum z position exceeded!")
            dest.append("%s%f" % (axis, 0.001*pos))
        dest = " ".join(sorted(dest))
        self.run("INCREMENTAL")
        self.run("LINEAR %s F%f" % (dest, 0.001*speed))


    def moveabs(self, speed, **axes):

        """ Move on one or more axes with the given speed in micrometers
        per second. The absolute positions are given in micrometers as
        named parameters. Example: moveabs(100, x=10327.7, z=2456.5)"""


        dest = []
        for axis, pos in axes.items():
            axis = self.normaxes(axis, "XYZAB")
            if axis == "Z":
                self.z = pos
                if self.z > self["zMax"]:
                    self.close()
                    raise RuntimeError("Maximum z position exceeded!")
            dest.append("%s%f" % (axis, 0.001*pos))
        dest = " ".join(sorted(dest))
        self.run("ABSOLUTE")
        self.run("LINEAR %s F%f" % (dest, 0.001*speed))


    def position(self, axes):

        """ Return current measured positions in micrometers on the
        given axes as a list of floating point numbers. Return a single
        number if a single axis is requested. """

        axes = self.normaxes(axes, "XYZAB")
        cmd = ["AXISSTATUS(%s, DATAITEM_PositionFeedback)" % a for a in axes]
        pos = [self.run(c) for c in cmd]
        pos = [1000 * float(p.replace(",", ".")) for p in pos]
        if len(pos) == 1:
            return pos[0]
        return pos


    def speed(self, axes):

        """ Return current measured speed in micrometers per second of
        the given axes as a list of floating point numbers. Return a
        single number if a single axis is requested. """

        axes = self.normaxes(axes, "XYZAB")
        cmd = ["AXISSTATUS(%s, DATAITEM_VelocityFeedback)" % a for a in axes]
        speed = [self.run(c) for c in cmd]
        speed = [1000 * float(p.replace(",", ".")) for p in speed]
        if len(speed) == 1:
            return speed[0]
        return speed


    def drivestatus(self, axes, wait=False):

        """ Return True, if all given axes are in position. Wait until
        all given axes are in position if the parameter wait is True.
        """

        axes = self.normaxes(axes, "XYZAB")
        cmd = ["AXISSTATUS(%s, DATAITEM_DriveStatus)" % a for a in axes]
        bitmask = DRIVESTATUS_InPosition
        if not wait:
            return all((int(self.run(c)) & bitmask) != 0 for c in cmd)

        while not all((int(self.run(c)) & bitmask) != 0 for c in cmd):
            pass
        return True


    def wait(self, axes, pause=None):

        """ Wait until all given axes are in position after pause
        milliseconds. """

        if pause is not None:
            time.sleep(0.001*pause)
        self.drivestatus(axes, True)


    def load(self, task, fn):

        """ Load AeroBasic program from given file and store it as task.
        Valid task numbers range from 1-32. """

        #print('PROGRAM %d LOAD "%s"' % (task, fn))
        self.run('PROGRAM %d LOAD "%s"' % (task, fn))


    def start(self, task):

        """ Start execution of the given task. """

        self.run("PROGRAM %d START" % task)


    def stop(self, task):

        """ Stop and remove the given task. """

        self.run("PROGRAM %d STOP" % task)


    def state(self, task):

        """ Return status of given task as integer value and as string.
        """

        state = int(self.run("TASKSTATUS(%d, DATAITEM_TaskState)" % task))
        return state, TASKSTATE[state]


    def attenuate(self, att):

        """ Set laser attenuator to given value in the range 0.0..10.0.
        """

        att = float(att)
        if att < 0.0 or att > 10.0:
            raise RuntimeError("Not a valid attenuator value: %g!" % att)
        self.run("$AO[0].A=%f" % att)


    def power(self, power):

        """ Set laser power to given value in milliwatts. """

        att = self.attenuator.ptoa(power)
        self.attenuate(att)
        
        
    def laseron(self, power):

        """ Switch laser on with given power. """

        self.power(power)
        self.run("GALVO LASEROVERRIDE A ON")


    def laseroff(self):

        """ Switch laser off. """

        self.run("GALVO LASEROVERRIDE A OFF")


    def pulse(self, power, duration):

        """ Deliver laser pulse with given power in milliwatts and
        duration in seconds. """

        self.laseron(power)
        time.sleep(duration)
        self.laseroff()


    def init_zline(self, fn=None):

        """ Load and compile zline program. """

        # Sanity check
        name = "zline"
        if name in self["tasks"]:
            return
        
        # Default file name
        if fn is None:
            fn = "__zline__.pgm"

        # First free task number
        tasks = self["tasks"].values()
        if len(tasks) == 0:
            task = 1
        else:
            task = min(set(range(1, max(tasks)+2)) - set(tasks))

        # Store AeroBasic program as file
        self["tasks"][name] = task
        self.task_pgms[name] = ZLINE_PGM
        with open(fn, "w") as fp:
            fp.write(self.task_pgms[name])

        # Stop any running program 1 
        self.stop(task)

        # Load AeroBasic program 1 from file
        path = os.path.join(os.getcwd(), fn)
        self.load(task, path)

        # Done
        return task

        
    def zline(self, power, fast, slow, dz):

        """ Run zline program with fast and slow speed in µm/s as well
        as axial distance in µm. Return when the program finished
        successfully and raise a RuntimeError otherwise. """

        # Initialize zline program
        name = "zline"
        if not name in self["tasks"]:
            self.init_zline()

        # Task number        
        task = self["tasks"][name]

        # Store task parameters as global variables
        if self.z + 0.5*dz > self["zMax"]:
            self.close()
            raise RuntimeError("Maximum z position exceeded!")
        self.run("$global[0] = %f" % (0.001*fast))
        self.run("$global[1] = %f" % (0.001*slow))
        self.run("$global[2] = %f" % (0.001*dz))

        # Set laser power
        self.power(power)

        # Run zline program
        self.start(task)
        state = TASKSTATE_ProgramRunning
        while state == TASKSTATE_ProgramRunning:
            state = int(self.run("TASKSTATUS(%d, DATAITEM_TaskState)" % task))

        # Program failure
        if state != TASKSTATE_ProgramComplete:
            self.close()
            raise RuntimeError("Task state '%s' (%d)!" \
                               % (TASKSTATE[state], state))


    def info(self):

        """ Return information dictionary. """

        keys = ("zMax", "systemDescription", "model", "manufacturer",
                "softwareVersion", "host", "port")
        return {k: self[k] for k in keys}
    

    def container(self, config=None, **kwargs):

        """ Return results as SciDataContainer. """

        # General metadata
        content = {
            "containerType": {"name": "MotionControl", "version": 1.1},
            }
        meta = {
            "title": "Motion control system parameters",
            "description": "Parameters of the Aerotech A3200 system.",
            }
        
        # Create container dictionary
        items = {
            "content.json": content,
            "meta.json": meta,
            "data/parameter.json": self.parameters(self.controller),
            }

        # Add program files
        for name, task in self["tasks"]:
            item = "data/%s.pgm" % name
            items[item] = self.task_pgms[name]

        # Return container object
        config = config or self.config
        return Container(items=items, config=config, **kwargs)
