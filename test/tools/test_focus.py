##########################################################################
# Copyright (c) 2022-2024 Reinhard Caspary                               #
# <reinhard.caspary@phoenixd.uni-hannover.de>                            #
# This program is free software under the terms of the MIT license.      #
##########################################################################

from nanofactorysystem import System, Focus, getLogger, mkdir

args = {
    "attenuator": {
        "fitKind": "quadratic",
        },
    "controller": {
        "zMax": 25700.0,
        },
    "sample": {
        "name": "#1",
        "orientation": "top",
        "substrate": "boro-silicate glass",
        "substrateThickness": 700.0,
        "material": "SZ2080",
        "materialThickness": 75.0,
        },
    "focus": {},
    }

user = "Reinhard"
objective = "Zeiss 20x"
path = mkdir(".test/focus")
logger = getLogger(logfile=f"{path}/console.log")

logger.info("Initialize system object...")
with System(user, objective, logger, **args) as system:
    
    logger.info("Initialize focus object...")
    focus = Focus(system, logger, **args)
    
    logger.info("Store background image...")
    focus.imgBack.write(f"{path}/back.zdc")
    
    logger.info("Expose vertical line and detect focus...")
    x = system.x0
    y = system.y0
    z = system.z0
    dz = 200.0
    power = 0.7
    speed= 200.0
    duration= 0.2
    focus.run(x, y, z, dz, power, speed, duration)
    
    logger.info("Store images...")
    focus.imgPre.write(f"{path}/image_pre.zdc")
    focus.imgPost.write(f"{path}/image_post.zdc")
    
    logger.info("Store results...")
    dc = focus.container()
    dc.write(f"{path}/focus.zdc")
    logger.info("Done.")
