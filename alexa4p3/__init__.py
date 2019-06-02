
#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2016 Kai Meder <kai@meder.info>
#  fork 2018 Andre Kohler <andre.kohler01@googlemail.com>
#########################################################################
#  This file is part of SmartHomeNG.
#
#  SmartHomeNG is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHomeNG is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHomeNG. If not, see <http://www.gnu.org/licenses/>.
#########################################################################
import os
import sys
import uuid



from lib.model.smartplugin import SmartPlugin
import logging
import json


from .device import AlexaDevices, AlexaDevice
from .action import AlexaActions
from .service import AlexaService

from . import actions_turn
from . import actions_temperature
from . import actions_percentage
from . import actions_lock
# Tools for Payload V3 

from . import p3_action





class Alexa4P3(SmartPlugin):
    PLUGIN_VERSION = "1.0.1"
    ALLOW_MULTIINSTANCE = False

    def __init__(self, sh, service_host='0.0.0.0', service_port=9000, service_https_certfile=None, service_https_keyfile=None):
        self.logger = logging.getLogger(__name__)
        self.sh = sh
        self.devices = AlexaDevices()
        self.actions = AlexaActions(self.sh, self.logger, self.devices)
        self.service = AlexaService(self.logger, self.PLUGIN_VERSION, self.devices, self.actions,
                                    service_host, int(service_port), service_https_certfile, service_https_keyfile)

    def run(self):
        self.validate_devices()
        self.create_alias_devices()
        self.service.start()
        self.alive = True

    def stop(self):
        self.service.stop()
        self.alive = False


    def parse_item(self, item):
        # device/appliance
        #self.logger.debug('Parse-Item')
        device_id = None
        if 'alexa_device' in item.conf:
            device_id = item.conf['alexa_device']
        
        #supported actions/directives
        action_names = None
        if 'alexa_actions' in item.conf:
            action_names = list( map(str.strip, item.conf['alexa_actions'].split(' ')) )
            self.logger.debug("Alexa: {}-actions = {}".format(item.id(), action_names))
            for action_name in action_names:
                if action_name and self.actions.by_name(action_name) is None:
                    self.logger.error("Alexa: invalid alexa action '{}' specified in item {}, ignoring item".format(action_name, item.id()))
                    return None

        # friendly name
        name = None
        name_is_explicit = None
        if 'alexa_name' in item.conf:
            name = item.conf['alexa_name']
            name_is_explicit = True
        elif action_names and 'name' in item.conf:
            name = item.conf['name']
            name_is_explicit = False
        
            
        # deduce device-id from name
        if name and not device_id:
            device_id = AlexaDevice.create_id_from_name(name)

        # skip this item if no device could be determined
        if device_id:
            self.logger.debug("Alexa: {}-device = {}".format(item.id(), device_id))
        else:
            return None # skip this item

        # create device if not yet existing
        if not self.devices.exists(device_id):
            self.devices.put( AlexaDevice(device_id) )

        device = self.devices.get(device_id)
              
        # types
        if 'alexa_types' in item.conf:
            device.types = list( map(str.strip, item.conf['alexa_types'].split(' ')) )
            self.logger.debug("Alexa: {}-types = {}".format(item.id(), device.types))

        # friendly name
        if name and (not device.name or name_is_explicit):
            self.logger.debug("Alexa: {}-name = {}".format(item.id(), name))
            if device.name and device.name != name:
                self.logger.warning("Alexa: item {} is changing device-name of {} from '{}' to '{}'".format(item.id(), device_id, device.name, name))
            device.name = name

        # friendly description
        if 'alexa_description' in item.conf:
            descr = item.conf['alexa_description']
            self.logger.debug("Alexa: {}-description = {}".format(item.id(), descr))
            if device.description and device.description != descr:
                self.logger.warning("Alexa: item {} is changing device-description of {} from '{}' to '{}'".format(item.id(), device_id, device.description, descr))
            device.description = descr

        # alias names
        if 'alexa_alias' in item.conf:
            alias_names = list( map(str.strip, item.conf['alexa_alias'].split(',')) )
            for alias_name in alias_names:
                self.logger.debug("Alexa: {}-alias = {}".format(item.id(), alias_name))
                device.alias.append(alias_name)

        # value-range
        if 'alexa_item_range' in item.conf:
            item_min_raw, item_max_raw = item.conf['alexa_item_range'].split('-')
            item_min = float( item_min_raw.strip() )
            item_max = float( item_max_raw.strip() )
            item.alexa_range = (item_min, item_max)
            self.logger.debug("Alexa: {}-range = {}".format(item.id(), item.alexa_range))

        # special turn on/off values
        if 'alexa_item_turn_on' in item.conf or 'alexa_item_turn_off' in item.conf:
            turn_on  = item.conf['alexa_item_turn_on']  if 'alexa_item_turn_on'  in item.conf else True
            turn_off = item.conf['alexa_item_turn_off'] if 'alexa_item_turn_off' in item.conf else False
            item.alexa_range = (turn_on, turn_off)
            self.logger.debug("Alexa: {}-range = {}".format(item.id(), item.alexa_range))
        
        # special ColorValue Type for RGB-devices
        if 'alexa_color_value_type' in item.conf:
            alexa_color_value_type = item.conf['alexa_color_value_type']
            device.alexa_color_value_type = alexa_color_value_type
            self.logger.debug("Alexa4P3: {}-ColorValueType = {}".format(item.id(), device.alexa_color_value_type))
            
            
        #===============================================
        #P3 - Properties
        #===============================================
        # ---- Start CamerStreamController

            
        
        i=1
        while i <= 3:
            myStream='alexa_stream_{}'.format(i)
            if myStream in item.conf:
                try:
                    camera_uri = item.conf[myStream]
                    camera_uri = json.loads(camera_uri)
                    device.camera_setting[myStream] =  camera_uri
                    self.logger.debug("Alexa4P3: {}-added Camera-Streams = {}".format(item.id(), camera_uri))
                    if 'alexa_csc_proxy_uri' in item.conf:
                        # Create a proxied URL for this Stream
                        myCam = str(uuid.uuid4().hex)
                        myProxiedurl ="%s%s%s" % (item.conf['alexa_csc_proxy_uri'], '/',myCam)
                        device.proxied_Urls['alexa_proxy_url-{}'.format(i)] = myProxiedurl
                        myNewEntry='alexa_proxy_url-{}'.format(i)
                        item.conf[myNewEntry]=myProxiedurl
                except Exception as e:
                    self.logger.debug("Alexa4P3: {}-wrong Stream Settings = {}".format(item.id(), camera_uri))
            i +=1    

        if 'alexa_csc_uri' in item.conf:
            camera_uri = item.conf['alexa_csc_uri']
            device.camera_uri = json.loads(camera_uri)
            self.logger.debug("Alexa4P3: {}-Camera-Uri = {}".format(item.id(), device.camera_uri))
            
        
        if 'alexa_auth_cred' in item.conf:
            alexa_auth_cred = item.conf['alexa_auth_cred']
            device.alexa_auth_cred = alexa_auth_cred
            self.logger.debug("Alexa4P3: {}-Camera-Auth = {}".format(item.id(), device.alexa_auth_cred))
            
        if 'alexa_camera_imageUri' in item.conf:
            alexa_camera_imageUri = item.conf['alexa_camera_imageUri']
            device.camera_imageUri = alexa_camera_imageUri
            self.logger.debug("Alexa4P3: {}-Camera-Image-Uri = {}".format(item.id(), device.camera_imageUri))
        # ---- Ende CamerStreamController    
        
        
        
        if 'alexa_thermo_config' in item.conf:
            thermo_config = item.conf['alexa_thermo_config']
            device.thermo_config =item.conf['alexa_thermo_config']
            self.logger.debug("Alexa4P3: {}-Thermo-Config = {}".format(item.id(), device.thermo_config))
        # Icon for Alexa-App - default = SWITCH
        if 'alexa_icon' in item.conf:
            icon = item.conf['alexa_icon']
            if not icon in str(device.icon):
                device.icon.append(icon)
                self.logger.debug("Alexa4P3: {}-added alexa_icon = {}".format(item.id(), device.icon))
        # allows to get status of ITEM, default = false
        if 'alexa_retrievable' in item.conf:
            retrievable = item.conf['alexa_retrievable']
            device.retrievable = retrievable
            self.logger.debug("Alexa4P3: {}-alexa_retrievable = {}".format(item.id(), device.retrievable))
        
        
        if 'alexa_proactivelyReported' in item.conf:
            proactivelyReported = item.conf['alexa_proactivelyReported']
            device.proactivelyReported = proactivelyReported
            self.logger.debug("Alexa4P3: {}-alexa_proactivelyReported = {}".format(item.id(), device.proactivelyReported))
        
            
        # register item-actions with the device
        if action_names:
            for action_name in action_names:
                device.register(action_name, item)
            self.logger.info("Alexa: {} supports {} as device {}".format(item.id(), action_names, device_id, device.supported_actions()))

        return None

    def _update_values(self):
        return None

    def validate_devices(self):
        for device in self.devices.all():
            self.logger.debug("Alexa: validating device {}".format(device.id))
            if not device.validate(self.logger):
                raise ValueError("Alexa: invalid device {}".format(device.id))

    def create_alias_devices(self):
        for device in self.devices.all():
            alias_devices = device.create_alias_devices()
            for alias_device in alias_devices:
                self.logger.info("Alexa: device {} aliased '{}' via {}".format(device.id, alias_device.name, alias_device.id))
                self.devices.put( alias_device )

        self.logger.info("Alexa: providing {} devices".format( len(self.devices.all()) ))
