#
import logging
import re
import os
import time

import plugin
import utils

logger = logging.getLogger('rcmServer' + '.' + __name__)

class Service(plugin.Plugin):

    COMMANDS = {'bash': None}

    def __init__(self, *args, **kwargs):
        super(Service, self).__init__(*args, **kwargs)

    def run_preload(self, key='PRELOAD_LINE', substitutions=None):
        logger.debug("GENERIC run_preload for service: "+ self.NAME)

        if key in self.templates:
            preload_command = self.templates[key]
            if substitutions:
                preload_command = utils.stringtemplate(preload_command).safe_substitute(substitutions)
            logger.info("Running preload command: " + preload_command)
            bash = self.COMMANDS.get('bash', None)
            params  = ["-c", preload_command]
            raw_output = bash( *params,
                             output=str)
            logger.info("Returned: " + raw_output)
        else:
            logger.info("preload command key: " + key + " NOT FOUND")
            for t in self.templates:
                logger.debug("plugin template: " + t + "--->" + str(self.templates[t]) + "<--")

    def search_logfile(self, logfile, regex_list=None, regex_list_key='START_REGEX_LIST', wait=1, timeout=0, timeout_key='TIMEOUT'):
        if regex_list == None:
            regex_list = self.templates.get(regex_list_key, [])
        try:
                timeout = timeout  + int(self.templates.get(timeout_key, '10'))
        except:
            timeout = 100

        if logfile and regex_list:
            regex_clist = []
            for regex_string in regex_list:
                logger.debug("compiling regex: -->"+ str(regex_string) + "<--")
                regex_clist.append(re.compile(str(regex_string),re.MULTILINE))

            secs = 0
            step = wait
            while (secs < timeout):
                if os.path.isfile(logfile):
                    #print(secs, "logfile:", logfile,)
                    f=open(logfile,'r')
                    with open(logfile, 'r') as f:
                        log_string=f.read()
                    #print("log_string:\n", log_string)
                    for r in regex_clist:
                        x = r.search(log_string)
                        if x:
                            return x.groupdict()
                secs+=step
                time.sleep(step)
            raise Exception("Timeouted (%d seconds) job not correcty running!!!" % (timeout) )
        raise Exception("Unable to search_logfile: %s with regex %s" % (logfile, str(regex_list)))

    def search_port(self, logfile='', timeout=0):
        for t in self.templates:
            logger.debug("+++++++++++ plugin template: "+ t+ "--->"+str(self.templates[t])+"<--")
        groupdict = self.search_logfile(logfile, timeout=timeout)
        node = ''
        port = 0
        for k in groupdict:
            logger.debug("+++++++++++ key: " + k + " ==> " + groupdict[k])
            if k == 'display' :
                port =  5900 + int(groupdict[k])
            if k == 'node' :
                node = groupdict[k]
            if k == 'port' :
                port = int(groupdict[k])

        return (node, port)





class TurboVNCServer(Service):
    def __init__(self):
        super(TurboVNCServer, self).__init__()
        self.NAME = "TurboVNC"



class Fake(Service):
    def __init__(self):
        super(Fake, self).__init__()
        self.NAME = "FakeService"

