import logging
import logging.config
import importlib
import os
import json
import socket
import copy
from collections import OrderedDict

# set prefix.
current_file = os.path.realpath(os.path.expanduser(__file__))
current_prefix = os.path.dirname(os.path.dirname(current_file))
current_etc_path = os.path.join(current_prefix, "etc")

import sys
current_path = os.path.dirname(os.path.dirname(current_file))
current_lib_path = os.path.join(current_path, "lib")
sys.path.insert(0, current_path)
sys.path.insert(0, current_lib_path)

# local import
import config
import jobscript_builder
import db
#import manager
import scheduler
from external import hiyapyco

import rcm
import enumerate_interfaces

logger = logging.getLogger('rcmServer')


class ServerManager:
    """
    The manager class.
    It is responsible to load from file the scheduler and service plugins.
    List of schedulers and services is written in a configuration yaml file
    """

    def __init__(self):
        self.schedulers = dict()
        self.services = dict()
        self.downloads = dict()
        self.root_node = None
        self.session_manager = db.SessionManager()
        self.login_fullname=''
        self.network_map = dict()

    def init(self):
        self.login_fullname = socket.getfqdn()


        self.configuration = config.getConfig('default')

        logging.config.dictConfig(self.configuration['logging_configs'])

        # load client download info
        self.downloads = self.configuration['download']



        # load plugins
        for scheduler_str in self.configuration['plugins', 'schedulers']:
            print(scheduler_str)
            try:
                module_name, class_name = scheduler_str.rsplit(".", 1)
                scheduler_class = getattr(importlib.import_module(module_name), class_name)
                scheduler_obj = scheduler_class()
                self.schedulers[scheduler_obj.NAME] = scheduler_obj
                logger.debug('loaded scheduler plugin ' +
                             scheduler_obj.__class__.__name__ +
                             " - " + scheduler_obj.NAME)
            except Exception as e:
                logger.error("plugin " + scheduler_str + " loading failed")
                logger.error(e)

        # load services
        for service_str in self.configuration['plugins', 'services']:
            try:
                module_name, class_name = service_str.rsplit(".", 1)
                service_class = getattr(importlib.import_module(module_name), class_name)
                service_obj = service_class()
                self.services[class_name] = service_obj
                logger.debug('loaded service plugin ' + service_obj.__class__.__name__ + " - " + service_obj.name)
            except Exception as e:
                logger.error("plugin loading failed")
                logger.error(e)

        # instantiate widget tree
        class_table = dict()
        class_table['SCHEDULER'] = (jobscript_builder.ConnectedManager, self.schedulers)

        self.root_node = jobscript_builder.AutoChoiceNode(name='TOP',
                                                          class_table=class_table)

    def map_login_name(self, subnet, nodelogin):
        logger.debug("mapping login " + nodelogin + " on network " + subnet)
        return self.configuration['network', subnet].get(nodelogin, nodelogin)

    def get_login_node_name(self, subnet=''):
        logger.debug("get_login")

        if (subnet):
            nodelogin = enumerate_interfaces.external_name(subnet)
            if (not nodelogin):
                nodelogin = self.login_fullname
            nodelogin = self.map_login_name(subnet, nodelogin)
            return nodelogin
        else:
            return self.login_fullname

    def get_checksum_and_url(self, build_platform):
        checksum = ""
        for download in self.downloads['checksum']:
            key = list(download.keys())[0]
            if key == build_platform:
                checksum = str(list(download.values())[0])

        downloadurl = ""
        for download in self.downloads['url']:
            key = list(download.keys())[0]
            if key == build_platform:
                downloadurl = str(list(download.values())[0])

        return checksum, downloadurl

    def get_jobscript_json_menu(self):
        return json.dumps(self.root_node.get_gui_options())

    def handle_choices(self,choices_string):
        choices=json.loads(choices_string)
        self.top_templates = self.root_node.substitute(choices)
        # here we find which scheduler has been selected.
        # not really robust... as it can be fooled if there are no substitution templates in yaml
        self.active_scheduler = None
        for sched_name,sched_obj in self.schedulers.items():
            if sched_obj.templates:
                self.active_scheduler = sched_obj
                break

    def new_session(self,
            sessionname='',
            subnet='',
            vncpassword_crypted=''):
        session_id = self.session_manager.new_session(tag=self.active_scheduler.NAME)
        new_session = rcm.rcm_session(sessionid=session_id,
                                      state='init',
                                      sessionname=sessionname,
                                      vncpassword=vncpassword_crypted)
        new_session.serialize(self.session_manager.session_file_path(session_id))

        print("login_name: ", self.get_login_node_name(subnet='49.57.50'))

        script = self.top_templates.get('SCRIPT', 'No script in templates')
        self.session_manager.write_jobscript(session_id, script)
        return session_id
