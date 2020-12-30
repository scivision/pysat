#!/usr/bin/env python
# Full license can be found in License.md
# Full author list can be found in .zenodo.json file
# DOI:10.5281/zenodo.1199703
# ----------------------------------------------------------------------------

import copy
import os

import json
from portalocker import Lock

import pysat.utils


class Parameters(object):
    """Stores user parameters used by pysat.

    Also stores custom user parameters provided the keys don't conflict with
    default pysat parameters.

    Attributes
    ----------
    data : dict
        pysat user settings dictionary
    defaults : dict
        Default parameters (keys) and values used by pysat
    file_path : str
        Location of file used to store settings
    non_defaults : list
        List of pysat parameters (strings) that don't have a defined
        default and are unaffected by self.restore_defaults().

    Note
    ----
    This method will look for 'pysat_settings.json' file first in the
    current working directory and then in the home '~/.pysat' directory.

    All pysat parameters are automatically stored whenever a parameter is
    assigned or modified.

    Default parameters and values tracked by this class:
        Values that map to the corresponding keywords on pysat.Instrument.
            'clean_level' : 'clean'
            'directory_format' : os.path.join('{platform}', '{name}', '{tag}')
            'ignore_empty_files': True
            'update_files': True

        Values that map to internal pysat settings:
            'file_timeout': 10; Window in time (seconds) that pysat will wait
                 to load/write a file while another thread uses that file
                 before giving up.

    pysat parameters without a working default value:
        'data_path': Stores location of top-level directory pysat uses to
            store and load data.
        'user_modules': Stores information on modules registered within pysat.
            Used by `pysat.utils.registry`

    """

    def __init__(self, path=None, create_new=False):
        """
        Parameters
        ----------
        path : str
            If provided, the directory path will be used to load/store a
            parameters file with name 'pysat_settings.json' (default=None).
        create_new : bool
            If True, a new parameters file is created. Will be created at path
            if provided. If not, file will be created in `pysat.pysat_dir`.

        """
        sfname = 'pysat_settings.json'
        self.data = {}
        self.file_path = None

        # Define default parameters and values
        dir_format = os.path.join('{platform}', '{name}', '{tag}')
        defaults = {'clean_level': 'clean',
                    'directory_format': dir_format,
                    'ignore_empty_files': True,
                    'file_timeout': 10,
                    'update_files': True}

        # Attach default parameters and values to object
        self.defaults = defaults

        # Define pysat parameters without a default setting
        non_defaults = ['data_dir', 'user_modules']
        self.non_defaults = non_defaults

        # If path provided, need to make a new parameters file. Load existing
        # file otherwise.
        if path is not None:
            # Create a new file using name provided
            self.file_path = os.path.join(path, sfname)
        else:
            # Cycle through locations and load any pysat parameter files found.
            # First, check current working directory, then pysat user directory.
            # Stop looking once an existing file is found.
            file_locs = [os.path.join('.', sfname),
                         os.path.join(os.path.expanduser('~'), '.pysat',
                                      sfname)]
            for fileloc in file_locs:
                if os.path.isfile(fileloc):
                    self.file_path = fileloc
                    break

        if create_new:
            self.clear_and_restart()
        else:
            # Ensure we have a valid file
            if self.file_path is None:
                estr = ''.join(('pysat is unable to locate a user settings ',
                                'file. Please check the locations, "./" or ',
                                '"~/.pysat" for the file "pysat_settings.json"',
                                '.'))
                raise RuntimeError(estr)

        # Load parameters in thread-safe manner.
        # Can't use user set file_timeout since we don't know what it is yet.
        # Can't use NetworkLock in pysat.utils either since this object (params)
        # doesn't exist yet.
        with Lock(self.file_path, 'r', timeout=10) as fout:
            self.data = json.load(fout)
            # In case of network files system
            fout.flush()
            os.fsync(fout.fileno())

        return

    def __repr__(self):
        """String describing MetaData instantiation parameters

        Returns
        -------
        out_str : str
            Simply formatted output string

        """

        out_str = ''.join(('Parameters(path=', self.file_path, ')'))
        return out_str

    def __str__(self, long_str=True):
        """String describing Meta instance, variables, and attributes

        Parameters
        ----------
        long_str : bool
            Return short version if False and long version if True
            (default=True)

        Returns
        -------
        out_str : str
            Nicely formatted output string

        """

        # Get typical pysat parameters (those with defaults)
        typical = list(self.defaults.keys())

        # Get pysat parameters without working defaults
        pparams = self.non_defaults

        # Get any additional parameters set by the user
        both = typical.copy()
        both.extend(pparams)
        users = [key for key in self.data.keys() if key not in both]

        # Print the short output
        out_str = "pysat Parameters object\n"
        out_str += "----------------------\n"
        out_str += "Tracking {:d} standards with defaults\n".format(len(typical))
        out_str += "Tracking {:d} standards no defaults\n".format(len(pparams))
        out_str += "Tracking {:d} user values\n".format(len(users))

        # Print the longer output
        if long_str:

            out_str += "\nStandard parameters:\n"
            for typ in typical:
                out_str += ''.join((typ, ' : ', self[typ].__str__(), '\n'))

            out_str += "\nStandard parameters (no defaults):\n"
            for typ in pparams:
                out_str += ''.join((typ, ' : ', self[typ].__str__(), '\n'))

            out_str += "\nUser parameters:\n"
            for typ in users:
                out_str += ''.join((typ, ' : ', self[typ].__str__(), '\n'))

        return out_str

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        # Update current settings
        # Some parameters require processing before storage.
        if key == 'data_dir':
            pysat.utils.set_data_dir(value, store=False)
            self.data['data_dir'] = pysat.data_dir
        else:
            # General or user parameter, no additional processing
            self.data[key] = value

        # Store settings in file
        with Lock(self.file_path, 'w', self['file_timeout']) as fout:
            json.dump(self.data, fout)
            # Ensure write is fully complete even for network file systems
            fout.flush()
            os.fsync(fout.fileno())

    def restore_defaults(self):
        """Restore default pysat parameters

        Does not modify any stored custom user keys or pysat parameters
        without a default value.

        """

        # Set default values for each of the pysat provided values. Set
        # all but the last parameter directly. Set last using __setitem__
        # to trigger a file write.
        keys = list(self.defaults.keys())
        for key in keys[:-1]:
            self.data[key] = self.defaults[key]

        # Set final item which also triggers a file write
        self[keys[-1]] = self.defaults[keys[-1]]

        return

    def clear_and_restart(self):
        """Clears all stored settings and sets pysat defaults

        pysat parameters without a default value are set to '' """

        # Clear current data and assign a copy of default values
        self.data = copy.deepcopy(self.defaults)

        # Set pysat parameters without a default value to ''
        for key in self.non_defaults[:-1]:
            self.data[key] = ''

        # Trigger a file write built into item assignment for last item
        self[self.non_defaults[-1]] = ''

        return