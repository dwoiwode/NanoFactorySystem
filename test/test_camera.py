##########################################################################
# Copyright (c) 2022-2024 Reinhard Caspary                               #
# <reinhard.caspary@phoenixd.uni-hannover.de>                            #
# This program is free software under the terms of the MIT license.      #
##########################################################################

from nanofactorysystem import Camera, getLogger, mkdir

args = {
    "ExposureTime": 15000,
    }

user = "Reinhard"
path = mkdir("test/camera")
logger = getLogger(logfile="%s/console.log" % path)
with Camera(user, logger, **args) as camera:
    logger.info("Exposure time %.4f ms" % (0.001*camera["ExposureTime"]))
    logger.info("Optimizing exposure time...")
    camera.optexpose()
    logger.info("Exposure time %.4f ms" % (0.001*camera["ExposureTime"]))
    dc = camera.container()
    dc.write("%s/image.zdc" % path)
    print(dc)
    logger.info("Done.")
