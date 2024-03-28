##########################################################################
# Copyright (c) 2023-2024 Reinhard Caspary                               #
# <reinhard.caspary@phoenixd.uni-hannover.de>                            #
# This program is free software under the terms of the MIT license.      #
##########################################################################
#
# This modules provides the class Parameter, which is used as base class for
# device or tool classes of the package NanoFactorySystem.
#
##########################################################################

import logging
from scidatacontainer import load_config

from .config import sysConfig


class Parameter(object):

    """ Prototype class providing a standardized interface to export
    parameters and results of an application class to a data packege
    object. """

    _defaults = {"dummy": None}

    def __init__(self, user, logger=None, **kwargs):

        # Initialize properties
        self._params = {}

        # Store user data dictionary
        self.user = sysConfig.user(user)
        self.config = load_config(
            author = self.user.get("name", None),
            email = self.user.get("email", None),
            organization = self.user.get("organization", None),
            orcid = self.user.get("orcid", None))
                
        # Store logger
        self.log = logger or logging
        
        # Store parameters
        if len(kwargs) != 1:
            raise RuntimeError("Unknown arguments section!")
        kwargs = list(kwargs.values())[0]
        for key, value in self._defaults.items():
            if key in kwargs:
                value = kwargs.pop(key)
            self[key] = value


    def __setitem__(self, key, value):

        """ Setter method to access class parameters using the
        dictionary syntax. """

        #print("Set", key, value)
        if hasattr(self, "device") and key in self.device.keys():
            self.device[key] = value
        elif key in self._defaults:
            self._params[key] = value
        else:
            raise KeyError("Unknown item %s!" % key)
        
        

    def __getitem__(self, key):

        """ Getter method to access class parameters using the
        dictionary syntax. """
        
        #print("Get", key)
        if hasattr(self, "device") and key in self.device.keys():
            value = self.device[key]
        elif key in self._defaults:
            value = self._params[key]
        else:
            raise KeyError("Unknown item %s!" % key)
        #print("Value", value)
        return value


    def keys(self):
        
        """ Return all parameter keys. """
        
        return list(sorted(self._params.keys()))
    

    def parameters(self):

        """ Return a copy of the parameter dictionary of this object updating
        the content of the optional dictionary default. """

        # New dictionary with current parameters
        params = dict(self._params)
        
        # Update optional device parameters
        if hasattr(self, "device"):
            if hasattr(self.device, "parameters"):
                params["device"] = self.device.parameters()
            elif hasattr(self.device, "keys"):
                for key in self.device.keys():
                    params[key] = self.device[key]
        
        # Done.
        return params
