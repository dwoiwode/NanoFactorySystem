##########################################################################
# Copyright (c) 2022-2024 Reinhard Caspary                               #
# <reinhard.caspary@phoenixd.uni-hannover.de>                            #
# This program is free software under the terms of the MIT license.      #
##########################################################################
#
# This module provides the system class for a laser direct writing
# system, which is the hardware interface used by the algorithm modules.
#
##########################################################################

import math
from scidatacontainer import Container

from . import ImageContainer
from .config import sysConfig, popargs
from .parameter import Parameter
from .devices import Camera, Dhm, A3200
from .tools import Transform


##########################################################################
class System(Parameter):

    """ Main class for the Femtika Nanofactory system. """

    _defaults = sysConfig.system | {
        "backOffset": -300.0,
        "speed": 2000.0,
        "delay": 10.0,
        }

    def __init__(self, user, objective, logger=None, **kwargs):

        """ Initialize the scanner algorithm. """

        # Not open now
        self.opened = False

        # Initialize parameter class
        args = popargs(kwargs, "system")
        super().__init__(user, logger, **args)
        self.log.info("Initializing system.")

        # Store objective data dictionary
        self.objective = sysConfig.objective(objective)

        # Initialize coordination system transformation object
        self.transform = Transform(self.objective)

        # Store optional sample data dictionary. Applications using the
        # system should include this item into their data container.
        self.sample = popargs(kwargs, "sample")

        # Initialize the MatrixVision camera
        args = popargs(kwargs, "camera")
        self.camera = Camera(user, self.objective, logger=self.log, **args)
        if not self.camera.opened:
            self.log.error("Can't connect to camera!")
            raise RuntimeError("Can't connect to camera!")

        # Initialize the LyncéeTec DHM
        args = popargs(kwargs, "dhm")
        self.dhm = Dhm(user, self.objective, logger=self.log, **args)
        if not self.dhm.opened:
            self.log.error("Can't connect to holographic microscope!")
            raise RuntimeError("Can't connect to holographic microscope!")

        # Initialize the Aerotech A3200 controller
        args = popargs(kwargs, ("attenuator", "controller"))
        self.controller = A3200(user, self.log, **args)
        self.controller.init_zline()

        # Center the galvo scanner
        self.controller.moveabs(100, a=0, b=0)

        # Current xyz positions
        self.x0, self.y0, self.z0 = self.controller.position("XYZ")
        if self.z0 > self.controller["zMax"]:
            raise RuntimeError("Maximum z position exceeded!")

        # Mark open state
        self.opened = True

        # Done
        self.log.info("Initialized system.")


    def close(self, home=True):

        """ Close connection to hardware devices. """

        if home and self.opened:
            self.home(wait=False)

        self.dhm.close()
        self.camera["AcquisitionMode"] = "Continuous"
        self.camera.close()

        try:
            self.controller.close()
        except AttributeError:
            pass

        self.opened = False
        self.log.info("System closed.")


    def __enter__(self):

        """ Context manager entry method. """

        return self


    def __exit__(self, errtype, value, tb):

        """ Context manager exit method. """

        #print("".join(traceback.format_exception(errtype, value, tb)))
        self.close()


    def update_pos(self, level, *args):

        """ Update camera calibration data. """

        self.transform.update(level, *args)


    def object_pos(self, v_px, vs=None):

        """ Return object coordinates from given camera image coordinates
        based on the given or current stage coordinates. Object and stage
        coordinates are absolute x,y,z coordinates in micrometres, image
        coordinates are x,y coordinates in pixels relative to the image
        centre. """

        if vs is None:
            vs = self.system.controller.position("XYZ")
        return self.transform.object_pos(v_px, vs)


    def camera_pos(self, v_um, vs=None):

        """ Return camera image coordinates from given object coordinates
        based on the given or current stage coordinates. Object and stage
        coordinates are absolute x,y,z coordinates in micrometres, image
        coordinates are x,y coordinates in pixels relative to the image
        centre. """

        if vs is None:
            vs = self.system.controller.position("XY")
        return self.transform.camera_pos(v_um, vs)


    def stage_pos(self, v_um, v_px):

        """ Return stage coordinates required to match the given object
        coordinates to the given image coordinates. Object and stage
        coordinates are absolute x,y,z coordinates in micrometres, image
        coordinates are x,y coordinates in pixels relative to the image
        centre. """

        return self.transform.stage_pos(v_um, v_px)


    def home(self, wait=False):

        """ Move stages to their home position. """

        self.controller.moveabs(self["speed"], a=0.0, b=0.0)
        self.controller.moveabs(self["speed"], x=self.x0, y=self.y0, z=self.z0)
        if wait:
            self.controller.wait("XYZ")
        self.log.debug(f"Moved to home position {self.x0:.0f}, {self.y0:.0f}, {self.z0:.0f}")


    def position(self, axes):

        """ Return current measured positions in micrometres on the
        given axes as a list of floating point numbers. Return a single
        number if a single axis is requested. """

        return self.controller.position(axes)


    def current_pos(self):

        """ Return a dictionary containing the current position of all axes
        in micrometres. """

        return dict(zip("xyzab", self.position("XYZAB")))


    def wait(self, axes, pause=None):

        """ Wait until all given axes are in position after pause
        milliseconds. """

        self.controller.wait(axes, pause)


    def moveabs(self, speed=None, wait=None, **axes):

        """ Move on one or more axes with the given speed in micrometers
        per second. The absolute positions are given in micrometers as
        named parameters. It is optional to name the axes for which to
        wait to be settled after the movement. """

        if speed is None:
            speed = self["speed"]
        self.controller.moveabs(speed, **axes)
        if wait is not None:
            wait_axes = "".join(axes.keys())
            self.controller.wait(wait_axes, wait)


    def pulse(self, power, duration):

        """ Deliver laser pulse with given power in milliwatts and
        duration in seconds. """

        self.controller.pulse(power, duration)


    def getimage(self) -> ImageContainer:

        """ Get a camera image and return an image container. """

        return self.camera.container()


    def optexpose(self, level=127):

        """ Set exposure time for given mean value of the image content.
        """

        return self.camera.optexpose(level)


    def polyline(self, line, power, speed, dia):

        """ Exposed a single 2D polyline with given laser power and
        exposure speed at the current position. The given approximate
        focus diameter is used to handle very short polylines. """

        x = [x for x, y in line]
        y = [y for x, y in line]
        llx = min(x)
        lly = min(y)
        urx = max(x)
        ury = max(y)
        size = math.sqrt((urx-llx)**2 + (ury-lly)**2)

        if size < 0.2*dia:
            x = 0.5*(llx+urx)
            y = 0.5*(lly+ury)
            self.controller.moveabs(self["speed"], x=x, y=y)
            self.pulse(power, 10*dia/speed)
        else:
            x, y = line[0]
            self.controller.moveabs(self["speed"], x=x, y=y)
            self.controller.laseron(power)
            for x, y in line[1:]:
                self.controller.moveabs(speed, x=x, y=y)
            self.controller.laseroff()


    def polylines(self, z, lines, power, speed, dia):

        """ Exposed a couple of 2D polylines with given laser power and
        exposure speed at the given z position. The given approximate
        focus diameter is used to handle very short polylines. """

        self.controller.moveabs(self["speed"], z=z)
        for line in lines:
            self.polyline(line, power, speed, dia)


    def dots(self, z, img, pitch, power, dt):

        """ Exposed the given 1 bit image as an array of laser pulses
        with given lateral pitch, laser power and pulse duration at the
        given z position. """

        self.controller.moveabs(self["speed"], z=z)
        x0, y0 = self.position("xy")
        h = len(img)
        for j, row in enumerate(img):
            y = y0 + (j-0.5*(h-1))*pitch
            w = len(row)
            for i, value in enumerate(row):
                x = x0 + (i-0.5*(w-1))*pitch
                if value > 0:
                    self.controller.moveabs(self["speed"], x=x, y=y)
                    self.pulse(power, dt)
        self.controller.moveabs(self["speed"], x=x0, y=y0)


    def zline(self, power, fast, slow, dz):

        """ Run zline program with fast and slow speed in µm/s as well
        as axial distance in µm. Return when the program finished
        successfully and raise a RuntimeError otherwise. """

        self.controller.zline(power, fast, slow, dz)


    def items(self):

        items = {
            "data/objective.json": self.objective,
            "data/controller.json": self.controller.parameters(),
            "data/camera.json": self.camera.parameters(),
            "data/dhm.json": self.dhm.parameters(),
            "data/system.json": self.parameters(),
            }
        if self.sample:
            items["data/sample.json"] = self.sample
        return items


    def container(self, config=None, **kwargs):

        """ Return system configuration as SciDataContainer. """

        # General metadata
        content = {
            "containerType": {"name": "NanoFactory", "version": 1.1},
            }
        meta = {
            "title": "System Configuration Data",
            "description": "Parameters of the Laser Nanofactory system.",
            }

        # Create container dictionary
        items = {
            "content.json": content,
            "meta.json": meta,
            } | self.items()

        # Return container object
        config = config or self.config
        return Container(items=items, config=config, **kwargs)
