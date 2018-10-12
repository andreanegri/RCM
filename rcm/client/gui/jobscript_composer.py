# stdlib
import json
import sys
import os
import copy
import glob
from collections import OrderedDict

root_rcm_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_rcm_path)

import utils


class CascadeYamlConfig:
    """
    singleton ( pattern from https://python-3-patterns-idioms-test.readthedocs.io/en/latest/Singleton.html )
    config class that parse cascading yaml files with hiyapyco
    constructor take a list of files that are parsed hierachically by parse method
    """

    class __CascadeYamlConfig:
        def __init__(self, list_paths=None):
            self._conf = OrderedDict()
            if list_paths:
                self.list_paths = list_paths
            else:
                self.list_paths = glob.glob(os.path.join(os.path.dirname(os.path.realpath(__file__)), "*.yaml"))

        def parse(self):
            print("CascadeYamlConfig: parsing: ", self.list_paths)
            if self.list_paths:
                self._conf = utils.hiyapyco.load(
                    *self.list_paths,
                    interpolate=True,
                    method=utils.hiyapyco.METHOD_MERGE,
                    failonmissingfiles=False
                )

        @property
        def conf(self):
            print("Getting value")
            return copy.deepcopy(self._conf)

        def __getitem__(self, nested_key_list=None):
            """
            this funchion access parsed config as loaded from hiyapyco
            :param nested_key_list: list of the nested keys to retrieve
            :return: deep copy of OrderedDict
            """
            val = self._conf
            if nested_key_list:
                for k in nested_key_list:
                    val = val.get(k, OrderedDict())
            return copy.deepcopy(val)

    instance = None

    def __init__(self, listpaths=None):
        if not CascadeYamlConfig.instance:
            CascadeYamlConfig.instance = CascadeYamlConfig.__CascadeYamlConfig(listpaths)
            CascadeYamlConfig.instance.parse()

    def __getattr__(self, name):
        return getattr(self.instance, name)

    def __getitem__(self, nested_key_list):
        return self.instance.__getitem__(nested_key_list)


class BaseGuiComposer(object):
    NAME = None
    working = True

    def __init__(self, schema=None, name=None, defaults=None, class_table=None):

        if name:
            self.NAME = name
        if schema:
            self.schema = schema
        else:
            # self.schema = CascadeYamlConfig().get_copy(['schema', self.NAME])
            self.schema = CascadeYamlConfig()['schema', self.NAME]
        if defaults:
            self.defaults = defaults
        else:
            self.defaults = CascadeYamlConfig()['defaults', self.NAME]
        if class_table:
            self.class_table = class_table
        else:
            self.class_table = dict()
        print(self.__class__.__name__, ": ", self.NAME)
        print("self.schema ", self.schema)
        print("self.defaults ", self.defaults)

    def substitute(self, choices):
        print("class:", self.__class__.__name__, "name:", self.NAME, choices)


class LeafGuiComposer(BaseGuiComposer):

    def get_gui_options(self):
        options = copy.deepcopy(self.schema)
        if 'values' in options:
            for preset in self.defaults:
                options['values'][preset] = self.defaults[preset]
        else:
            options['values'] = copy.deepcopy(self.defaults)
        return options

    def substitute(self, choices):
        for key, value in choices.items():
            print("in leaf: ", self.NAME, "substitute ", key + " : " + value)


class CompositeComposer(BaseGuiComposer):

    def __init__(self, *args, **kwargs):
        super(CompositeComposer, self).__init__(*args, **kwargs)
        self.children = []

    def add_child(self, child):
        self.children.append(child)

    def get_gui_options(self):
        options = OrderedDict()
        for child in self.children:
            options[child.NAME] = child.get_gui_options()
        return options

    def substitute(self, choices):
        BaseGuiComposer.substitute(self, choices)
        for child in self.children:
            child.substitute(choices)


class ChoiceGuiComposer(CompositeComposer):

    def get_gui_options(self):
        composer_options = self.schema
        composer_choice = OrderedDict()
        if self.children:
            for child in self.children:
                composer_choice[child.NAME] = child.get_gui_options()
            composer_options['choices'] = composer_choice
        if 'list' in composer_options:
            del composer_options['list']
        return composer_options


class AutoChoiceGuiComposer(CompositeComposer):

    def __init__(self, *args, **kwargs):
        super(AutoChoiceGuiComposer, self).__init__(*args, **kwargs)

        for child_name in self.schema:
            child_schema = copy.deepcopy(self.schema[child_name])
            if child_name in self.defaults:
                if 'list' in child_schema:
                    manager_class = self.class_table.get(child_name, AutoManagerChoiceGuiComposer)
                    child = manager_class(name=child_name,
                                          schema=copy.deepcopy(child_schema),
                                          defaults=copy.deepcopy(self.defaults[child_name]))
                else:
                    print("hadling leaf item-->", child_name)
                    child = LeafGuiComposer(name=child_name,
                                            schema=copy.deepcopy(child_schema),
                                            defaults=copy.deepcopy(self.defaults[child_name]))
                self.add_child(child)
            else:
                if 'list' in child_schema:
                    print("skipping complex item -->", child_name, "in schema but not in defaults")
                else:
                    print("adding leaf item -->", child_name, "without defaults")
                    child = LeafGuiComposer(name=child_name,
                                            schema=copy.deepcopy(child_schema),
                                            defaults=OrderedDict())
                    self.add_child(child)

    def substitute(self, choices):
        BaseGuiComposer.substitute(self, choices)
        child_subst = dict()
        for child in self.children:
            child_subst[child] = dict()
        for key, value in choices.items():
            # print("--in: ", self.NAME, "substitute ", key + " : " + value)
            subkey = key.split('.')
            # print(subkey)
            for child in self.children:
                if child.NAME == subkey[0]:
                    # print("stripping subst", self.NAME, "--", '.'.join(subkey[1:]) )
                    child_subst[child][key] = value
        for child in self.children:
            if child_subst[child]:
                # print(child_subst[child])
                child.substitute(child_subst[child])


class ManagedChoiceGuiComposer(AutoChoiceGuiComposer):

    def get_gui_options(self):
        options = OrderedDict()
        for child in self.children:
            options[child.NAME] = child.get_gui_options()
        return {'list': options}


class ManagerChoiceGuiComposer(ChoiceGuiComposer):

    def substitute(self, choices):
        BaseGuiComposer.substitute(self, choices)
        child_subst = dict()
        active_child_name = choices.get(self.NAME, '')
        for child in self.children:
            child_subst[child] = dict()
        for key, value in choices.items():
            # print("--in: ", self.NAME, "substitute ", key + " : " + value)
            subkey = key.split('.')
            # print(subkey)
            if len(subkey) > 1:
                if self.NAME == subkey[0]:
                    for child in self.children:
                        if child.NAME == active_child_name:
                            # print("stripping subst", self.NAME, "--", '.'.join(subkey[1:]) )
                            child_subst[child]['.'.join(subkey[1:])] = value
        for child in self.children:
            if child_subst[child]:
                # print(child_subst[child])
                child.substitute(child_subst[child])


class AutoManagerChoiceGuiComposer(ManagerChoiceGuiComposer):

    def __init__(self, *args, **kwargs):
        super(AutoManagerChoiceGuiComposer, self).__init__(*args, **kwargs)
        if 'list' in self.schema:
            for class_name in self.defaults:
                print("handling child  : ", class_name)
                child = ManagedChoiceGuiComposer(name=class_name,
                                                 schema=copy.deepcopy(self.schema['list']),
                                                 defaults=copy.deepcopy(self.defaults.get(class_name, OrderedDict())))
                self.add_child(child)


class BaseScheduler(ManagedChoiceGuiComposer):
    """
    Base scheduler class, pattern taken form https://python-3-patterns-idioms-test.readthedocs.io/en/latest/Factory.html
    """
    NAME = None

    def __init__(self, *args, **kwargs):
        """
        General scheduler class,
        :param schema: accept a schema to override schema that are retrieved through CascadeYamlConfig singleton
        """
        merged_defaults = copy.deepcopy(kwargs['defaults'])
        for param in ['ACCOUNT', 'QUEUE']:
            if param in kwargs:
                print("---------------------------------")
                merged_defaults[param] = self.merge_list(merged_defaults.get(param, OrderedDict()),
                                                         kwargs.get(param, []))
                del kwargs[param]
        kwargs['defaults'] = merged_defaults
        super(BaseScheduler, self).__init__(*args, **kwargs)

    def merge_list(self, preset, computed):
        print("merging:", preset, "----", computed)
        out = copy.deepcopy(preset)
        for a in computed:
            if a not in out:
                if hasattr(out, 'append'):
                    out.append(a)
                else:
                    out[a] = OrderedDict()
        print("merged:", out)
        return out


class TrueScheduler(BaseScheduler):

    commands = {}

    def __init__(self, *args, **kwargs):
        for c in self.commands:
            exe = utils.which(c)
            if exe:
                self.commands[c] = exe
                print("command: ", c, " Found !!!!")
            else:
                self.working = self.working and False
                print("command: ", c, " Not Found !!!!")
        kwargs['ACCOUNT'] = self.valid_accounts()
        kwargs['QUEUE'] = self.get_queues()
        super(TrueScheduler, self).__init__(*args, **kwargs)

    def valid_accounts(self):
        return ['dummy_account_1', 'dummy_account_2']

    def get_queues(self):
        return ['dummy_queue_1', 'dummy_queue_2']


class SlurmScheduler(TrueScheduler):
    NAME = 'Slurm'
    commands = {'sshare': None, 'sinfo': None}

    def __init__(self, *args, **kwargs):
        # super().__init__(schema=schema)
        # BaseScheduler.__init__(self,schema=schema)
        #self.commands = {'sshare': None, 'sinfo': None}
        super(SlurmScheduler, self).__init__(*args, **kwargs)


    def get_all_accounts(self):
        # sshare --parsable -a
        # Eric: sshare --parsable --format %
        # saldo -b
        # Lstat.py
        sshare = self.commands.get('sshare', None)
        if sshare:
            out = sshare(
                '--parsable',
                output=str
            )
            accounts = []
            for l in out.splitlines()[1:]:
                accounts.append(l.split('|')[0])
            return accounts
        else:
            return []

    def validate_account(self, account):
        return True

    def valid_accounts(self):
        accounts = []
        for a in self.get_all_accounts():
            if self.validate_account(a):
                accounts.append(a)
        return accounts

    def get_queues(self):
        # hints on useful slurm commands
        # sacctmgr show qos
        print("Slurm get queues !!!!")
        sinfo = self.commands.get('sinfo', None)
        if sinfo:
            out = sinfo(
                '--format=%P',
                output=str
            )
            partitions = []
            for l in out.splitlines()[1:]:
                partitions.append(l)
            print("Slurm found queues:", partitions, "!!!!")
            return partitions
        else:
            print("warning !!!!!! sinfo:", sinfo)
            return []


class PBSScheduler(TrueScheduler):
    NAME = 'PBS'
    #commands = {'qstat': None}

class LocalScheduler(BaseScheduler):
    NAME = 'Local'


class SSHScheduler(BaseScheduler):
    NAME = 'SSH'


class SchedulerManager(ManagerChoiceGuiComposer):
    NAME = 'SCHEDULER'
    SCHEDULERS = [SlurmScheduler, PBSScheduler, LocalScheduler]

    def __init__(self, *args, **kwargs):
        super(SchedulerManager, self).__init__(*args, **kwargs)
        if 'list' in self.schema:
            for class_name in self.defaults:
                print("handling child  : ", class_name)
                managed_class = ManagedChoiceGuiComposer
                for sched_class in self.SCHEDULERS:
                    if sched_class.NAME == class_name:
                        managed_class = sched_class
                        break
                child = managed_class(name=class_name,
                                      schema=copy.deepcopy(self.schema['list']),
                                      defaults=copy.deepcopy(self.defaults.get(class_name, OrderedDict())))
                if child.working:
                    self.add_child(child)


if __name__ == '__main__':
    config = CascadeYamlConfig()
    if True:
        root = AutoChoiceGuiComposer(schema=config.conf['schema'], defaults=config.conf['defaults'], class_table={'SCHEDULER': SchedulerManager})
    else:
        schedulers = SchedulerManager()
        root = CompositeComposer()
        root.add_child(schedulers)
        # root.add_child(ManagerChoiceGuiComposer(name='SCHEDULER'))
        root.add_child(LeafGuiComposer(name='DIVIDER'))
        root.add_child(ManagerChoiceGuiComposer(name='SERVICE'))
    out = root.get_gui_options()
    # out=sched.get_gui_options(accounts=['minnie','clarabella'],queues=['prima_coda_indefinita','gll_user_prd'])
    print("Root-->" + json.dumps(out, indent=4))
