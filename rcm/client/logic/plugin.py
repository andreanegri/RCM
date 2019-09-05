# std lib
import sys
import os
import json
import pexpect
import subprocess

# local includes
import client.logic.rcm_utils as rcm_utils
from client.miscellaneous.logger import logic_logger
from client.utils.pyinstaller_utils import resource_path
import client.logic.cipher as cipher
from client.miscellaneous.config_parser import parser, defaults


class Executable(object):
    """Class representing a program that can be run on the command line."""

    def __init__(self, name):
        self.exe = name.split(' ')
        self.default_env = {}
        self.returncode = None

        # if not self.exe:
        #    raise ProcessError("Cannot construct executable for '%s'" % name)

    def add_default_arg(self, arg):
        """Add a default argument to the command."""
        self.exe.append(arg)

    def add_arg_value(self, arg, value):
        """Add a default argument to the command."""
        self.exe.append(arg)
        self.exe.append(value)

    def add_default_env(self, key, value):
        """Set an environment variable when the command is run.

        Parameters:
            key: The environment variable to set
            value: The value to set it to
        """
        self.default_env[key] = value

    @property
    def command(self):
        """The command-line string.

        Returns:
            str: The executable and default arguments
        """
        return ' '.join(self.exe)

    @property
    def name(self):
        """The executable name.

        Returns:
            str: The basename of the executable
        """
        return os.path.basename(self.path)

    @property
    def path(self):
        """The path to the executable.

        Returns:
            str: The path to the executable
        """
        return self.exe[0]


class TurboVNCExecutable(Executable):
    def __init__(self):

        self.set_env()

        if sys.platform.startswith('darwin'):
            exe = "open"
        else:
            exe = rcm_utils.which('vncviewer')
            if not exe :
                logic_logger.error("vncviewer not found! Check the PATH environment variable.")
            if sys.platform == 'win32':
                # if the executable path contains spaces, it has to be put inside apexes
                exe = "\"" + exe + "\""
            # self.exe = exe
            logic_logger.debug("vncviewer path: " + exe)

        super(TurboVNCExecutable, self).__init__(exe)

    def set_env(self):
        # set the environment
        if getattr(sys, 'frozen', False):
            logic_logger.debug("Running in a bundle")
            # if running in a bundle, we hardcode the path
            # of the built-in vnc viewer and plink (windows only)
            os.environ['JAVA_HOME'] = resource_path('turbovnc')
            if sys.platform == 'win32':
                # on windows 10, administration policies prevent execution  of external programs
                # located in %TEMP% ... it seems that it cannot be loaded

                home_path = os.path.expanduser('~')
                desktop_path = os.path.join(home_path, 'Desktop')
                exe_dir_path = os.path.dirname(sys.executable)
                if os.path.exists(desktop_path):
                    rcm_unprotected_path = os.path.join(exe_dir_path, '.rcm', 'executables')
                    os.makedirs(rcm_unprotected_path, exist_ok=True)
                    dest_dir = os.path.join(rcm_unprotected_path, 'turbovnc')
                    rcm_utils.copytree(resource_path('turbovnc'), dest_dir)
                    os.environ['JAVA_HOME'] = dest_dir

            os.environ['JDK_HOME'] = os.environ['JAVA_HOME']
            os.environ['JRE_HOME'] = os.path.join(os.environ['JAVA_HOME'], 'jre')
            os.environ['CLASSPATH'] = os.path.join(os.environ['JAVA_HOME'], 'lib') + \
                                      os.pathsep + os.path.join(os.environ['JRE_HOME'], 'lib')
            os.environ['PATH'] = os.path.join(os.environ['JAVA_HOME'], 'bin') + os.pathsep + os.environ['PATH']
            logic_logger.debug("JAVA_HOME: " + str(os.environ['JAVA_HOME']))
            logic_logger.debug("JRE_HOME: " + str(os.environ['JRE_HOME']))
            logic_logger.debug("JDK_HOME: " + str(os.environ['JDK_HOME']))
            logic_logger.debug("CLASSPATH: " + str(os.environ['CLASSPATH']))
        logic_logger.debug("PATH: " + str(os.environ['PATH']))

    def build(self, session, local_portnumber):
        nodelogin = session.hash['nodelogin']
        # local_portnumber = rcm_utils.get_unused_portnumber()

        tunnel = session.hash['tunnel']
        try:
            tunnelling_method = json.loads(parser.get('Settings', 'ssh_client'))
        except Exception:
            tunnelling_method = "internal"
        logic_logger.info("Using " + str(tunnelling_method) + " ssh tunnelling")

        # Decrypt password
        vncpassword = session.hash.get('vncpassword', '')
        rcm_cipher = cipher.RCMCipher()
        vncpassword_decrypted = rcm_cipher.decrypt(vncpassword)

        # Darwin
        if sys.platform.startswith('darwin'):
            self.add_arg_value("-W", "vnc://:" + vncpassword_decrypted + "@127.0.0.1:" + str(local_portnumber))

        # Win64
        elif sys.platform == 'win32':
            self.add_default_arg("/nounixlogin")
            self.add_default_arg("/noreconnect")
            self.add_default_arg("/nonewconn")
            self.add_arg_value("/loglevel", str(rcm_utils.vnc_loglevel))
            self.add_arg_value("/password", vncpassword_decrypted)

        # Linux
        else:
            self.add_arg_value("-quality", "80")
            self.add_arg_value("-password", vncpassword_decrypted)
            self.add_default_arg("-noreconnect")
            self.add_default_arg("-nonewconn")

        if not sys.platform.startswith('darwin'):
            if tunnel == 'y':
                self.add_default_arg("127.0.0.1:" + str(local_portnumber))
            else:
                self.add_default_arg(nodelogin + ":" + session.hash['display'])


class SSHExecutable(Executable):
    def __init__(self):

        self.set_env()

        # ssh executable
        if sys.platform == 'win32':
            exe = rcm_utils.which('PLINK')
        else:
            exe = rcm_utils.which('ssh')
        if not exe:
            if sys.platform == 'win32':
                logic_logger.error("plink.exe not found! Check the PATH environment variable.")
            else:
                logic_logger.error("ssh not found!")
            return
        if sys.platform == 'win32':
            # if the executable path contains spaces, it has to be put inside apexes
            exe = "\"" + exe + "\""

        super(SSHExecutable, self).__init__(exe)

    def set_env(self):
        return

    def build(self, user, password, session, local_portnumber):
        node = session.hash['node']
        nodelogin = session.hash['nodelogin']

        portstring = session.hash.get('port', '')
        if portstring:
            portnumber = int(portstring)
        else:
            portnumber = 5900 + int(session.hash['display'])

        self.add_arg_value("-L", "127.0.0.1:" + str(local_portnumber) + ":" + node + ":" + str(portnumber) )
        self.add_default_arg(user + "@" + nodelogin)

        if sys.platform == 'win32':
            self.add_default_arg("-ssh")
            self.add_arg_value("-pw", str(password))


class NativeSSHTunnelForwarder(object):
    def __init__(self, tunnel_command, password):
        self.tunnel_command = tunnel_command
        self.tunnel_process = None
        self.password = password


    def __enter__(self):
        logic_logger.debug(self.tunnel_command)
        if sys.platform == 'win32':
            self.tunnel_process = subprocess.Popen(self.tunnel_command,
                                                   bufsize=1,
                                                   stdout=subprocess.PIPE,
                                                   stderr=subprocess.PIPE,
                                                   stdin=subprocess.PIPE,
                                                   shell=False,
                                                   universal_newlines=True,
                                                   env=os.environ)
            while True:
                o = self.tunnel_process.stderr.readline()
                logic_logger.debug("tunnel process stderr: " + str(o.strip()))

                if o.strip().split()[0] == 'Store':
                   break
                if o.strip().split()[0] == 'Using':
                   break
                if o.strip().split()[0] == 'connection.':
                   self.tunnel_process.stdin.write("yes\r\n")
                   continue

        else:
            self.tunnel_process = pexpect.spawn(self.tunnel_command,
                                                timeout=50)

            i = self.tunnel_process.expect(['continue connecting',
                                            'password',
                                            r'.+',
                                            pexpect.TIMEOUT,
                                            pexpect.EOF],
                                            timeout=5)

            if i == 0:
                self.tunnel_process.sendline('yes')
                i = self.tunnel_process.expect(['continue connecting',
                                                'password',
                                                pexpect.TIMEOUT,
                                                pexpect.EOF],
                                                timeout=5)

            if i == 1:
                self.tunnel_process.sendline(self.password)

    def __exit__(self, exc_type, exc_value, tb):
        self.stop()

    def stop(self):
        logic_logger.debug("Stopping ssh tunnelling")

        if self.tunnel_process:
            if sys.platform == 'win32':
                logic_logger.debug("Killing ssh tunnel process " +
                                   str(self.tunnel_process.pid))
                self.tunnel_process.terminate()
            else:
                self.tunnel_process.close(force=True)
