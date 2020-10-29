from copy import deepcopy as deepcopy
import os
import warnings
import numpy as np
import pandas as pds

import pysat
import pysat.utils._core as core_utils


class Meta(object):
    """ Stores metadata for Instrument instance, similar to CF-1.6 netCDFdata
    standard.

    Parameters
    ----------
    metadata : pandas.DataFrame
        DataFrame should be indexed by variable name that contains at minimum
        the standard_name (name), units, and long_name for the data stored in
        the associated pysat Instrument object.
    labels : dict
        Dict where keys are the label attribute names and the values are tuples
        that have the label values and value types in that order.
        (default={'units': ('units', str), 'name': ('long_name', str),
                  'notes': ('notes', str), 'desc': ('desc', str),
                  'plot': ('plot_label', str), 'axis': ('axis', str),
                  'scale': ('scale', str), 'min_val': ('value_min', float),
                  'max_val': ('value_max', float), 'fill_val': ('fill', float)})

    Attributes
    ----------
    data : pandas.DataFrame
        index is variable standard name, 'units', 'long_name', and other
        defaults are also stored along with additional user provided labels.
    labels : MetaLabels
        Labels for MetaData attributes

    Note
    ----
    Meta object preserves the case of variables and attributes as it first
    receives the data. Subsequent calls to set new metadata with the same
    variable or attribute will use case of first call. Accessing or setting
    data thereafter is case insensitive. In practice, use is case insensitive
    but the original case is preserved. Case preseveration is built in to
    support writing files with a desired case to meet standards.

    Metadata for higher order data objects, those that have
    multiple products under a single variable name in a pysat.Instrument
    object, are stored by providing a Meta object under the single name.

    Supports any custom metadata values in addition to the expected metadata
    attributes (units, name, notes, desc, plot_label, axis, scale, value_min,
    value_max, and fill). These base attributes may be used to programatically
    access and set types of metadata regardless of the string values used for
    the attribute. String values for attributes may need to be changed
    depending upon the standards of code or files interacting with pysat.

    Meta objects returned as part of pysat loading routines are automatically
    updated to use the same values of plot_label, units_label, etc. as found
    on the pysat.Instrument object.

    Examples
    --------
    ::

        # instantiate Meta object, default values for attribute labels are used
        meta = pysat.Meta()
        # set a couple base units
        # note that other base parameters not set below will
        # be assigned a default value
        meta['name'] = {'long_name': string, 'units': string}
        # update 'units' to new value
        meta['name'] = {'units': string}
        # update 'long_name' to new value
        meta['name'] = {'long_name': string}
        # attach new info with partial information, 'long_name' set to 'name2'
        meta['name2'] = {'units': string}
        # units are set to '' by default
        meta['name3'] = {'long_name': string}

        # assigning custom meta parameters
        meta['name4'] = {'units': string, 'long_name': string
                         'custom1': string, 'custom2': value}
        meta['name5'] = {'custom1': string, 'custom3': value}

        # assign multiple variables at once
        meta[['name1', 'name2']] = {'long_name': [string1, string2],
                                    'units': [string1, string2],
                                    'custom10': [string1, string2]}

        # assiging metadata for n-Dimensional variables
        meta2 = pysat.Meta()
        meta2['name41'] = {'long_name': string, 'units': string}
        meta2['name42'] = {'long_name': string, 'units': string}
        meta['name4'] = {'meta': meta2}

        # or
        meta['name4'] = meta2
        meta['name4'].children['name41']

        # mixture of 1D and higher dimensional data
        meta = pysat.Meta()
        meta['dm'] = {'units': 'hey', 'long_name': 'boo'}
        meta['rpa'] = {'units': 'crazy', 'long_name': 'boo_whoo'}
        meta2 = pysat.Meta()
        meta2[['higher', 'lower']] = {'meta': [meta, None],
                                      'units': [None, 'boo'],
                                      'long_name': [None, 'boohoo']}

        # assign from another Meta object
        meta[key1] = meta2[key2]

        # access fill info for a variable, presuming default label
        meta[key1, 'fill']

        # access same info, even if 'fill' not used to label fill values
        meta[key1, meta.fill_label]


        # change a label used by Meta object
        # note that all instances of fill_label
        # within the meta object are updated
        meta.fill_label = '_FillValue'
        meta.plot_label = 'Special Plot Variable'

        # this feature is useful when converting metadata within pysat
        # so that it is consistent with externally imposed file standards

    """

    # -----------------------------------------------------------------------
    # Define the magic methods

    def __init__(self, metadata=None,
                 labels={'units': ('units', str), 'name': ('long_name', str),
                         'notes': ('notes', str), 'desc': ('desc', str),
                         'plot': ('plot_label', str), 'axis': ('axis', str),
                         'scale': ('scale', str),
                         'min_val': ('value_min', float),
                         'max_val': ('value_max', float),
                         'fill_val': ('fill', float)}):

        # set mutability of Meta attributes
        self.mutable = True

        # Set the labels
        self.labels = MetaLabels(**labels)

        # init higher order (nD) data structure container, a dict
        self._ho_data = {}

        # use any user provided data to instantiate object with data
        # attribute unit and name labels are called within
        if metadata is not None:
            if isinstance(metadata, pds.DataFrame):
                self._data = metadata

                # make sure defaults are taken care of for required metadata
                self.accept_default_labels(self)
            else:
                raise ValueError(''.join(('Input must be a pandas DataFrame',
                                          'type. See other constructors for',
                                          ' alternate inputs.')))
        else:
            columns = [mlab for mlab in dir(self.labels) if not callable(mlab)]
            self._data = pds.DataFrame(None, columns=columns)

        # establish attributes intrinsic to object, before user can
        # add any
        self._base_attr = dir(self)

    def __repr__(self):
        """String describing MetaData instantiation parameters

        Returns
        -------
        out_str : str
            Simply formatted output string

        """
        nvar = len([kk for kk in self.keys()])
        out_str = ''.join(['Meta(metadata=', self._data.__repr__(),
                           ', labels=', self.labels.__repr__(),
                           ') -> {:d} Variables'.format(nvar)])
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
        # Get the desired variables as lists
        labs = [var for var in self.attrs()]
        vdim = [var for var in self.keys() if var not in self.keys_nD()]
        nchild = {var: len([kk for kk in self[var]['children'].keys()])
                  for var in self.keys_nD()}
        ndim = ["{:} -> {:d} children".format(var, nchild[var])
                for var in self.keys_nD()]

        # Get the lengths of each list
        nlabels = len(labs)
        nvdim = len(vdim)
        nndim = len(ndim)

        # Print the short output
        out_str = "pysat Meta object\n"
        out_str += "-----------------\n"
        out_str += "Tracking {:d} metadata values\n".format(nlabels)
        out_str += "Metadata for {:d} standard variables\n".format(nvdim)
        out_str += "Metadata for {:d} ND variables\n".format(nndim)

        # Print the longer output
        if long_str:
            # Print all the metadata labels
            out_str += "\n{:s}".format(self.labels.__str__())

            # Print a subset of the metadata variables, divided by order
            ncol = 3
            max_num = 6  # Should be divible by 2 and ncol
            if nvdim > 0:
                out_str += "\nStandard Metadata variables:\n"
                out_str += core_utils.fmt_output_in_cols(vdim, ncols=ncol,
                                                         max_num=max_num)
            if nndim > 0:
                out_str += "\nND Metadata variables:\n"
                out_str += core_utils.fmt_output_in_cols(ndim, ncols=ncol,
                                                         max_num=max_num)

        return out_str

    def __setattr__(self, name, value):
        """Conditionally sets attributes based on self.mutable flag

        Parameters
        ----------
        name : str
            Attribute name to be assigned to Meta
        value : str or boolean
            String to be assigned to attribute specified by name or boolean
            if name is 'mutable'

        Note
        ----
        @properties are assumed to be mutable.

        We avoid recursively setting properties using
        method from https://stackoverflow.com/a/15751135

        """

        # mutable handled explicitly to avoid recursion
        if name != 'mutable':

            # check if this attribute is a property
            propobj = getattr(self.__class__, name, None)
            if isinstance(propobj, property):
                # check if the property is settable
                if propobj.fset is None:
                    raise AttributeError(''.join("can't set attribute - ",
                                                 "property has no fset"))

                # make mutable in case fset needs it to be
                mutable_tmp = self.mutable
                self.mutable = True

                # set the property
                propobj.fset(self, value)

                # restore mutability flag
                self.mutable = mutable_tmp
            else:
                # a normal attribute
                if self.mutable:
                    # use Object to avoid recursion
                    super(Meta, self).__setattr__(name, value)
                else:
                    raise AttributeError(''.join(("cannot set attribute - ",
                                                  "object's attributes are",
                                                  "immutable")))
        else:
            super(Meta, self).__setattr__(name, value)

    def __setitem__(self, names, input_data):
        """Convenience method for adding metadata.

        Parameters
        ----------
        names : str, list
            Data variable names for the input metadata
        input_data : dict, pds.Series, or Meta
            Input metadata to be assigned

        """

        if isinstance(input_data, dict):
            # if not passed an iterable, make it one
            if isinstance(names, str):
                names = [names]
                for key in input_data:
                    input_data[key] = [input_data[key]]
            elif isinstance(names, slice) and (names.step is None):
                # Check for instrument[indx,:] or instrument[idx] usage
                names = list(self.data.keys())

            # Make sure the variable names are in good shape.  The Meta
            # object is case insensitive, but case preserving.  Convert given
            # names into ones Meta has already seen.  If new, then input names
            # become the standard
            names = [self.var_case_name(name) for name in names]
            for name in names:
                if name not in self:
                    self._insert_default_values(name)
            # check if input dict empty
            if input_data.keys() == []:
                # Meta wasn't actually assigned by user.  This is an empty call
                # and we can head out - we've assigned defaults if first data.
                return
            # Perform some checks on the data and make sure number of inputs
            # matches number of metadata inputs.
            for key in input_data:
                if len(names) != len(input_data[key]):
                    raise ValueError(''.join(('Length of names and inputs',
                                              ' must be equal.')))
            # Make sure the attribute names are in good shape.  Check the
            # attribute's name against existing attribute names.  If the
            # attribute name exists somewhere, then the case of the existing
            # attribute will be enforced upon new data by default for
            # consistency.
            keys = [i for i in input_data]
            for name in keys:
                new_name = self.attr_case_name(name)
                if new_name != name:
                    input_data[new_name] = input_data.pop(name)

            # time to actually add the metadata
            for key in input_data:
                if key not in ['children', 'meta']:
                    for i, name in enumerate(names):
                        to_be_set = input_data[key][i]
                        if hasattr(to_be_set, '__iter__') and \
                                not isinstance(to_be_set, str):
                            # we have some list-like object
                            # can only store a single element
                            if len(to_be_set) == 0:
                                # empty list, ensure there is something
                                to_be_set = ['']
                            if isinstance(to_be_set[0], str) or \
                                    isinstance(to_be_set, bytes):
                                if isinstance(to_be_set, bytes):
                                    to_be_set = to_be_set.decode("utf-8")

                                self._data.loc[name, key] = '\n\n'.join(
                                    to_be_set)
                            else:
                                warnings.warn(' '.join(('Array elements are',
                                                        'not allowed in meta.',
                                                        'Dropping input :',
                                                        key)))
                        else:
                            self._data.loc[name, key] = to_be_set
                else:
                    # key is 'meta' or 'children'
                    # process higher order stuff. Meta inputs could be part of
                    # larger multiple parameter assignment
                    # so not all names may actually have 'meta' to add
                    for j, (item, val) in enumerate(zip(names,
                                                        input_data['meta'])):
                        if val is not None:
                            # assign meta data, recursive call....
                            # heads to if Meta instance call
                            self[item] = val

        elif isinstance(input_data, pds.Series):
            # Outputs from Meta object are a Series. Thus this takes in input
            # from a Meta object. Set data using standard assignment via a dict
            in_dict = input_data.to_dict()
            if 'children' in in_dict:
                child = in_dict.pop('children')
                if child is not None:
                    # if not child.data.empty:
                    self.ho_data[names] = child

            # remaining items are simply assigned
            self[names] = in_dict

        elif isinstance(input_data, Meta):
            # dealing with higher order data set
            # names is only a single name here (by choice for support)
            if (names in self._ho_data) and (input_data.empty):
                # no actual metadata provided and there is already some
                # higher order metadata in self
                return

            # get Meta approved variable names
            new_item_name = self.var_case_name(names)

            # Ensure that Meta labels of object to be assigned are
            # consistent with self.  input_data accepts self's labels
            input_data.accept_default_labels(self)

            # Go through and ensure Meta object to be added has variable and
            # attribute names consistent with other variables and attributes
            # this covers custom attributes not handled by default routine
            # above
            attr_names = input_data.attrs()
            new_names = []
            for name in attr_names:
                new_names.append(self.attr_case_name(name))
            input_data.data.columns = new_names

            # Same thing for variables
            var_names = input_data.data.index
            new_names = []
            for name in var_names:
                new_names.append(self.var_case_name(name))
            input_data.data.index = new_names

            # Assign Meta object now that things are consistent with Meta
            # object settings, but first make sure there are lower dimension
            # metadata parameters, passing in an empty dict fills in defaults
            # if there is no existing metadata info
            self[new_item_name] = {}

            # now add to higher order data
            self._ho_data[new_item_name] = input_data
        return

    def __getitem__(self, key):
        """Convenience method for obtaining metadata.

        Maps to pandas DataFrame.loc method.

        Parameters
        ----------
        key : str, tuple, or list
            A single variable name, a tuple, or a list

        Raises
        ------
        KeyError
            If a properly formatted key is not present
        NotImplementedError
            If the input is not one of the allowed data types

        Examples
        --------
        ::

            meta['name']
            meta['name1', 'units']
            meta[['name1', 'name2'], 'units']
            meta[:, 'units']

            # for higher order data
            meta['name1', 'subvar', 'units']
            meta['name1', ('units', 'scale')]

        """
        # Define a local convenience function
        def match_name(func, var_name, index_or_column):
            """Applies func on input variables(s) depending on variable type
            """
            if isinstance(var_name, str):
                # If variable is a string, use it as input
                return func(var_name)
            elif isinstance(var_name, slice):
                # If variable is a slice, use it to select data from the
                # supplied index or column input
                return [func(var) for var in index_or_column[var_name]]
            else:
                # Otherwise, assume the variable iterable input
                return [func(var) for var in var_name]

        # Access desired metadata based on key data type
        if isinstance(key, tuple):
            # If key is a tuple, looking at index, column access pattern
            if len(key) == 2:
                # If tuple length is 2, index, column
                new_index = match_name(self.var_case_name, key[0],
                                       self.data.index)
                new_name = match_name(self.attr_case_name, key[1],
                                      self.data.columns)
                return self.data.loc[new_index, new_name]

            elif len(key) == 3:
                # If tuple length is 3, index, child_index, column
                new_index = self.var_case_name(key[0])
                new_child_index = self.var_case_name(key[1])
                new_name = self.attr_case_name(key[2])
                return self.ho_data[new_index].data.loc[new_child_index,
                                                        new_name]

        elif isinstance(key, list):
            # If key is a list, selection works as-is
            return self[key, :]

        elif isinstance(key, str):
            # If key is a string, treatment varies based on metadata dimension
            if key in self:
                # Get case preserved string for variable name
                new_key = self.var_case_name(key)

                # Don't need to check if in lower, all variables are always in
                # the lower metadata.
                #
                # Assign meta_row using copy to avoid pandas
                # SettingWithCopyWarning, as suggested in
                # https://www.dataquest.io/blog/settingwithcopywarning/
                meta_row = self.data.loc[new_key].copy()
                if new_key in self.keys_nD():
                    meta_row.at['children'] = self.ho_data[new_key].copy()
                else:
                    meta_row.at['children'] = None  # Return empty meta instance

                return meta_row
            else:
                raise KeyError('Key not found in MetaData')
        else:
            raise NotImplementedError("".join(["No way to handle MetaData key ",
                                               "{}; ".format(key.__repr__()),
                                               "expected tuple, list, or str"]))

    # QUESTION: DOES THIS NEED TO CHANGE???
    def __contains__(self, other):
        """case insensitive check for variable name

        Parameters
        ----------
        other : Meta
            Meta object from which the default labels are obtained

        Returns
        -------
        does_contain : boolean
            True if input Meta class contains the default labels, False if it
            does not

        """
        does_contain = False

        if other.lower() in [i.lower() for i in self.keys()]:
            does_contain = True

        if not does_contain:
            if other.lower() in [i.lower() for i in self.keys_nD()]:
                does_contain = True

        return does_contain

    def __eq__(self, other_meta):
        """ Check equality between Meta instances

        Parameters
        ----------
        other_meta : Meta
            A second Meta class object

        Returns
        -------
        bool
            True if equal, False if not equal

        Note
        ----
        Good for testing.

        Checks if variable names, attribute names, and metadata values
        are all equal between to Meta objects. Note that this comparison
        treats np.NaN == np.NaN as True.

        Name comparison is case-sensitive.

        """

        if isinstance(other_meta, Meta):
            # check first if variables and attributes are the same
            # quick check on length
            keys1 = [i for i in self.keys()]
            keys2 = [i for i in other_meta.keys()]
            if len(keys1) != len(keys2):
                return False

            # now iterate over each of the keys in the first one
            # don't need to iterate over second one, if all of the first
            # in the second we are good. No more or less items in second from
            # check earlier.
            for key in keys1:
                if key not in keys2:
                    return False

            # do same checks on attributes
            attrs1 = [i for i in self.attrs()]
            attrs2 = [i for i in other_meta.attrs()]
            if len(attrs1) != len(attrs2):
                return False

            for attr in attrs1:
                if attr not in attrs2:
                    return False

            # now check the values of all elements now that we know all
            # variable and attribute names are the same
            for key in self.keys():
                for attr in self.attrs():
                    if not (self[key, attr] == other_meta[key, attr]):
                        # np.nan is not equal to anything
                        # if both values are NaN, ok in my book
                        try:
                            if not (np.isnan(self[key, attr])
                                    and np.isnan(other_meta[key, attr])):
                                # one or both are not NaN and they aren't equal
                                # test failed
                                return False
                        except TypeError:
                            # comparison above gets unhappy with string inputs
                            return False

            # check through higher order products
            # in the same manner as code above
            keys1 = [i for i in self.keys_nD()]
            keys2 = [i for i in other_meta.keys_nD()]
            if len(keys1) != len(keys2):
                return False

            for key in keys1:
                if key not in keys2:
                    return False

            # do same check on all sub variables within each nD key
            for key in self.keys_nD():
                keys1 = [i for i in self[key].children.keys()]
                keys2 = [i for i in other_meta[key].children.keys()]
                if len(keys1) != len(keys2):
                    return False

                for key_check in keys1:
                    if key_check not in keys2:
                        return False

                # check if attributes are the same
                attrs1 = [i for i in self[key].children.attrs()]
                attrs2 = [i for i in other_meta[key].children.attrs()]
                if len(attrs1) != len(attrs2):
                    return False

                for attr in attrs1:
                    if attr not in attrs2:
                        return False

                # now time to check if all elements are individually equal
                for key2 in self[key].children.keys():
                    for attr in self[key].children.attrs():
                        if not (self[key].children[key2, attr]
                                == other_meta[key].children[key2, attr]):
                            try:
                                nan_self = np.isnan(self[key].children[key2,
                                                                       attr])
                                nan_other = np.isnan(other_meta[key].children[
                                    key2, attr])
                                if not (nan_self and nan_other):
                                    return False
                            except TypeError:
                                # comparison above gets unhappy with string
                                # inputs
                                return False
            # if we made it this far, things are good
            return True
        else:
            # wasn't even the correct class
            return False

    # -----------------------------------------------------------------------
    # Define the hidden methods

    def _insert_default_values(self, data_var):
        """Set the default label values for a data variable

        Parameters
        ----------
        data_var : str
            Name of the data variable

        Note
        ----
        Sets NaN for all float values, -1 for all int values, and '' for all
        str values except for 'scale', which defaults to 'linear', and None
        for any othere data type.

        """
        # Cycle through each label type to create a list off label names
        # and label default values
        labels = list()
        default_vals = list()
        for lattr in self.labels.label_type.keys():
            labels.append(getattr(self.labels, lattr))
            default_vals.append(self.labels.default_values_from_attr(lattr))

        # Assign the default values to the DataFrame for this data variable
        self._data.loc[data_var, labels] = default_vals

        return

    def _label_setter(self, new_label, current_label, attr_label, default_type,
                      use_names_default=False):
        """Generalized setter of default meta attributes

        Parameters
        ----------
        new_label : str
            New label to use in the Meta object
        current_label : str
            The current label for the hidden attribute that is to be updated
            and stores the metadata
        attr_label : str
            The attribute label for the hidden attribute that is to be updated
            and stores the metadata
        default_type : type
            Type of value to be stored
        use_names_default : bool
            if True, MetaData variable names are used as the default
            value for the specified Meta attributes settings (default=False)

        Examples
        --------
        :

            @name_label.setter
            def name_label(self, new_label):
                self._label_setter(new_label, self._name_label,
                                    use_names_default=True)

        Note
        ----
        Not intended for end user

        """

        if new_label not in self.attrs():
            # New label not in metadata
            if current_label in self.attrs():
                # Current label exists and has expected case
                self.data.loc[:, new_label] = self.data.loc[:, current_label]
                self.data = self.data.drop(current_label, axis=1)
            else:
                if self.has_attr(current_label):
                    # There is a similar label with different capitalization
                    current_label = self.attr_case_name(current_label)
                    self.data.loc[:, new_label] = self.data.loc[:,
                                                                current_label]
                    self.data = self.data.drop(current_label, axis=1)
                else:
                    # There is no existing label, setting for the first time
                    if use_names_default:
                        self.data[new_label] = self.data.index
                    else:
                        default_val = self.labels.default_values_from_type(
                            default_type)
                        self.data[new_label] = default_val

            # Check higher order structures and recursively change labels
            for key in self.keys_nD():
                setattr(self.ho_data[key], attr_label, new_label)

        # Update the 'hidden' attribute value: current_label -> new_label
        setattr(self, ''.join(('_', attr_label)), new_label)

        return

    # -----------------------------------------------------------------------
    # Define the public methods and properties

    @property
    def ho_data(self):
        return self._ho_data

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, new_frame):
        self._data = new_frame

    @ho_data.setter
    def ho_data(self, new_dict):
        self._ho_data = new_dict

    @property
    def empty(self):
        """Return boolean True if there is no metadata
        """

        # only need to check on lower data since lower data
        # is set when higher metadata assigned
        if self.data.empty:
            return True
        else:
            return False

    def merge(self, other):
        """Adds metadata variables to self that are in other but not in self.

        Parameters
        ----------
        other : pysat.Meta

        """

        for key in other.keys():
            if key not in self:
                # copies over both lower and higher dimensional data
                self[key] = other[key]
        return

    def drop(self, names):
        """Drops variables (names) from metadata.

        Parameters
        ----------
        names : list-like
            List of string specifying the variable names to drop

        """

        # drop lower dimension data
        self.data = self._data.drop(names, axis=0)

        # drop higher dimension data
        for name in names:
            if name in self._ho_data:
                _ = self._ho_data.pop(name)
        return

    def keep(self, keep_names):
        """Keeps variables (keep_names) while dropping other parameters

        Parameters
        ----------
        keep_names : list-like
            variables to keep

        """
        # Create a list of variable names to keep
        keep_names = [self.var_case_name(name) for name in keep_names]

        # Get a list of current variable names
        current_names = self._data.index

        # Build a list of variable names to drop
        drop_names = [name for name in current_names if name not in keep_names]

        # Drop names not specified in keep_names list
        self.drop(drop_names)
        return

    def apply_meta_labels(self, other_meta):
        """Applies the existing meta labels from self onto different MetaData

        Parameters
        ----------
        other_meta : Meta
            Meta object to have default labels applied

        Returns
        -------
        other_updated : Meta
            Meta object with the default labels applied

        """
        # Create a copy of other, to avoid altering in place
        other_updated = other_meta.copy()

        # Update the Meta labels
        other_updated.labels = self.labels

        # Return the updated Meta class object
        return other_updated

    def accept_default_labels(self, other):
        """Applies labels for default meta labels from other onto self.

        Parameters
        ----------
        other : Meta
            Meta object to take default labels from

        """

        self.labels = other.labels
        return

    def var_case_name(self, name):
        """Provides stored name (case preserved) for case insensitive input

        If name is not found (case-insensitive check) then name is returned,
        as input. This function is intended to be used to help ensure the
        case of a given variable name is the same across the Meta object.

        Parameters
        ----------
        name : str
            variable name in any case

        Returns
        -------
        out_name : str
            string with case preserved as in metaobject

        """

        lower_name = name.lower()
        if name in self:
            for out_name in self.keys():
                if lower_name == out_name.lower():
                    return out_name

            for out_name in self.keys_nD():
                if lower_name == out_name.lower():
                    return out_name
        else:
            out_name = name

        return out_name

    def keys(self):
        """Yields variable names stored for 1D variables"""

        for ikey in self.data.index:
            yield ikey

    def keys_nD(self):
        """Yields keys for higher order metadata"""

        for ndkey in self.ho_data:
            yield ndkey

    def attrs(self):
        """Yields metadata products stored for each variable name"""

        for dcol in self.data.columns:
            yield dco

    def hasattr_case_neutral(self, attr_name):
        """Case-insensitive check for attribute names in this class

        Parameters
        ----------
        attr_name : str
            name of attribute to find

        Returns
        -------
        has_name : bool
            True if case-insesitive check for attribute name is True

        Note
        ----
        Does not check higher order meta objects

        """
        has_name = False

        if name.lower() in [dcol.lower() for dcol in self.data.columns]:
            has_name = True

        return has_name

    def attr_case_name(self, name):
        """Returns preserved case name for case insensitive value of name.

        Parameters
        ----------
        name : str
            name of variable to get stored case form

        Returns
        -------
        out_name : str
            name in proper case

        Note
        ----
        Checks first within standard attributes. If not found there, checks
        attributes for higher order data structures. If not found, returns
        supplied name as it is available for use. Intended to be used to help
        ensure that the same case is applied to all repetitions of a given
        variable name.

        """
        lower_name = name.lower()
        for out_name in self.attrs():
            if lower_name == out_name.lower():
                return out_name

        # check if attribute present in higher order structures
        for key in self.keys_nD():
            for out_name in self[key].children.attrs():
                if lower_name == out_name.lower():
                    return out_name

        # nothing was found if still here
        # pass name back, free to be whatever
        return name

    def concat(self, other, strict=False):
        """Concats two metadata objects together.

        Parameters
        ----------
        other : Meta
            Meta object to be concatenated
        strict : bool
            if True, ensure there are no duplicate variable names
            (default=False)

        Note
        ----
        Uses units and name label of self if other is different

        Returns
        -------
        mdata : Meta
            Concatenated object

        """

        mdata = self.copy()

        # checks
        if strict:
            for key in other.keys():
                if key in mdata:
                    raise RuntimeError(''.join(('Duplicated keys (variable ',
                                                'names) across Meta ',
                                                'objects in keys().')))
            for key in other.keys_nD():
                if key in mdata:
                    raise RuntimeError(''.join(('Duplicated keys (variable ',
                                                'names) across Meta '
                                                'objects in keys_nD().')))

        # make sure labels between the two objects are the same
        other_updated = self.apply_default_labels(other)

        # concat 1D metadata in data frames to copy of
        # current metadata
        for key in other_updated.keys():
            mdata.data.loc[key] = other.data.loc[key]

        # add together higher order data
        for key in other_updated.keys_nD():
            mdata.ho_data[key] = other.ho_data[key]

        return mdata

    def copy(self):
        """Deep copy of the meta object."""
        return deepcopy(self)

    def pop(self, label_name):
        """Remove and return metadata about variable

        Parameters
        ----------
        label_name : str
            Meta key for a data variable

        Returns
        -------
        output: pandas.Series
            Series of metadata for variable

        """
        # check if present
        if label_name in self:
            # get case preserved name for variable
            new_name = self.var_case_name(label_name)

            # check if 1D or nD
            if new_name in self.keys():
                output = self[new_name]
                self.data = self.data.drop(new_name, axis=0)
            else:
                output = self.ho_data.pop(new_name)
        else:
            raise KeyError('Key not present in metadata variables')

        return output

    def transfer_attributes_to_instrument(self, inst, strict_names=False):
        """Transfer non-standard attributes in Meta to Instrument object.

        Parameters
        ----------
        inst : pysat.Instrument
            Instrument object to transfer attributes to
        strict_names : boolean (False)
            If True, produces an error if the Instrument object already
            has an attribute with the same name to be copied.

        Note
        ----
        Pysat's load_netCDF and similar routines are only able to attach
        netCDF4 attributes to a Meta object. This routine identifies these
        attributes and removes them from the Meta object. Intent is to
        support simple transfers to the pysat.Instrument object.

        Will not transfer names that conflict with pysat default attributes.

        """

        # base Instrument attributes
        banned = inst._base_attr

        # get base attribute set, and attributes attached to instance
        base_attrb = self._base_attr
        this_attrb = dir(self)

        # collect these attributes into a dict
        adict = {}
        transfer_key = []
        for key in this_attrb:
            if key not in banned:
                if key not in base_attrb:
                    # don't store _ leading attributes
                    if key[0] != '_':
                        adict[key] = self.__getattribute__(key)
                        transfer_key.append(key)

        # store any non-standard attributes in Instrument get list of
        # instrument objects attributes first to check if a duplicate
        # instrument attributes stay with instrument
        inst_attr = dir(inst)

        for key in transfer_key:
            if key not in banned:
                if key not in inst_attr:
                    inst.__setattr__(key, adict[key])
                else:
                    if not strict_names:
                        # new_name = 'pysat_attr_'+key
                        inst.__setattr__(key, adict[key])
                    else:
                        rerr = ''.join(('Attribute ', key, 'attached to the '
                                        'Meta object can not be transferred ',
                                        'as it already exists in the ',
                                        'Instrument object.'))
                        raise RuntimeError(rerr)
        return

    @classmethod
    def from_csv(cls, filename=None, col_names=None, sep=None, **kwargs):
        """Create instrument metadata object from csv.

        Parameters
        ----------
        filename : string
            absolute filename for csv file or name of file stored in pandas
            instruments location
        col_names : list-like collection of strings
            column names in csv and resultant meta object
        sep : string
            column seperator for supplied csv filename
        **kwargs : dict
            Optional kwargs used by pds.read_csv

        Note
        ----
        column names must include at least ['name', 'long_name', 'units'],
        assumed if col_names is None.

        """
        req_names = ['name', 'long_name', 'units']
        if col_names is None:
            col_names = req_names
        elif not all([i in col_names for i in req_names]):
            raise ValueError('col_names must include name, long_name, units.')

        if sep is None:
            sep = ','

        if filename is None:
            raise ValueError('Must supply an instrument module or file path.')
        elif not isinstance(filename, str):
            raise ValueError('Keyword name must be related to a string')
        elif not os.path.isfile(filename):
            # Not a real file, assume input is a pysat instrument name
            # and look in the standard pysat location.
            testfile = os.path.join(pysat.__path__[0], 'instruments', filename)
            if os.path.isfile(testfile):
                filename = testfile
            else:
                # Try to form an absolute path, if the relative path failed
                testfile = os.path.abspath(filename)
                if not os.path.isfile(testfile):
                    raise ValueError("Unable to create valid file path.")
                else:
                    filename = testfile

        mdata = pds.read_csv(filename, names=col_names, sep=sep, **kwargs)

        if not mdata.empty:
            # Make sure the data name is the index
            mdata.index = mdata['name']
            del mdata['name']
            return cls(metadata=mdata)
        else:
            raise ValueError(''.join(['Unable to retrieve information from ',
                                      filename]))

    # TODO
    # @classmethod
    # def from_nc():
    #     """not implemented yet, load metadata from netCDF"""
    #     pass
    #
    # @classmethod
    # def from_dict():
    #     """not implemented yet, load metadata from dict of items/list types
    #     """
    #     pass


class MetaLabels(object):
    """ Stores metadata labels for Instrument instance

    Parameters
    ----------
    units : str
        String used to label units in storage. (default='units')
    name : str
        String used to label name in storage. (default='long_name')
    notes : str
        String used to label 'notes' in storage. (default='notes')
    desc : str
        String used to label variable descriptions in storage.
        (default='desc')
    plot : str
        String used to label variables in plots. (default='label')
    axis : str
        Label used for axis on a plot. (default='axis')
    scale : str
        string used to label plot scaling type in storage. (default='scale')
    min_val : str
        String used to label typical variable value min limit in storage.
        (default='value_min')
    max_val : str
        String used to label typical variable value max limit in storage.
        (default='value_max')
    fill_val : str
        String used to label fill value in storage. (default='fill') per
        netCDF4 standard
    export_nan: list
         List of labels that should be exported even if their value is nan.
         By default, metadata with a value of nan will be exluded from export.


    Attributes
    ----------
    data : pandas.DataFrame
        index is variable standard name, 'units', 'long_name', and other
        defaults are also stored along with additional user provided labels.
    units_label : str
        String used to label units in storage. (default='units'.
    name_label : str
        String used to label long_name in storage. (default='long_name'.
    notes_label : str
       String used to label 'notes' in storage. (default='notes'
    desc_label : str
       String used to label variable descriptions in storage.
       (default='desc'
    plot_label : str
       String used to label variables in plots. (default='label'
    axis_label : str
        Label used for axis on a plot. (default='axis'
    scale_label : str
       string used to label plot scaling type in storage. (default='scale'
    min_label : str
       String used to label typical variable value min limit in storage.
       (default='value_min'
    max_label : str
       String used to label typical variable value max limit in storage.
       (default='value_max'
    fill_label : str
        String used to label fill value in storage. (default='fill' per
        netCDF4 standard

    Note
    ----
    Meta object preserves the case of variables and attributes as it first
    receives the data. Subsequent calls to set new metadata with the same
    variable or attribute will use case of first call. Accessing or setting
    data thereafter is case insensitive. In practice, use is case insensitive
    but the original case is preserved. Case preseveration is built in to
    support writing files with a desired case to meet standards.

    Metadata for higher order data objects, those that have
    multiple products under a single variable name in a pysat.Instrument
    object, are stored by providing a Meta object under the single name.

    Supports any custom metadata values in addition to the expected metadata
    attributes (units, name, notes, desc, plot_label, axis, scale, value_min,
    value_max, and fill). These base attributes may be used to programatically
    access and set types of metadata regardless of the string values used for
    the attribute. String values for attributes may need to be changed
    depending upon the standards of code or files interacting with pysat.

    Meta objects returned as part of pysat loading routines are automatically
    updated to use the same values of plot_label, units_label, etc. as found
    on the pysat.Instrument object.

    """

    def __init__(self, units=('units', str), name=('long_name', str),
                 notes=('notes', str), desc=('desc', str), plot=('plot', str),
                 axis=('axis', str), scale=('scale', str),
                 min_val=('value_min', float), max_val=('value_max', float),
                 fill_val=('fill', float), **kwargs):
        """ Initialize the MetaLabels class

        Parameters
        ----------
        units : tuple
            Units label name and value type (default=('units', str))
        name : tuple
            Name label name and value type (default=('long_name', str))
        notes : tuple
            Notes label name and value type (default=('notes', str))
        desc : tuple
            Description label name and value type (default=('desc', str))
        plot : tuple
            Plot label name and value type (default=('plot', str))
        axis : tuple
            Axis label name and value type (default=('axis', str))
        scale : tuple
            Scale label name and value type (default=('scale', str))
        min_val : tuple
            Minimum value label name and value type
            (default=('value_min', float))
        max_val : tuple
            Maximum value label name and value type
            (default=('value_max', float))
        fill_val : tuple
            Fill value label name and value type (default=('fill', float))
        kwargs : dict
            Dictionary containing optional label attributes, where the keys
            are the attribute names and the values are tuples containing the
            label name and value type

        """

        # Initialize a dictionary of label types, whose keys are the label
        # attributes
        self.label_type = {'units': units[1], 'name': name[1],
                           'notes': notes[1], 'desc': desc[1], 'plot': plot[1],
                           'axis': axis[1], 'scale': scale[1],
                           'min_val': min_val[1], 'max_val': max_val[1],
                           'fill_val': fill_val[1]}

        # Set the default labels and types
        self.units = units[0]
        self.name = name[0]
        self.notes = notes[0]
        self.desc = desc[0]
        self.plot = plot[0]
        self.axis = axis[0]
        self.scale = scale[0]
        self.min_val = min_val[0]
        self.max_val = max_val[0]
        self.fill_val = fill_val[0]

        # Set the custom labels and label types
        for custom_label in kwargs.keys():
            setattr(self, custom_label, kwargs[custom_label][0])
            self.label_type[custom_label] = kwargs[custom_label][1]

        return

    def __repr__(self):
        """String describing MetaData instantiation parameters

        Returns
        -------
        out_str : str
            Simply formatted output string

        """
        label_str = ', '.join(["{:s}={:}".format(mlab, getattr(self, mlab))
                               for mlab in dir(self) if not callable(mlab)])
        out_str = ''.join(['MetaLabels(', label_str, ")"])
        return out_str

    def __str__(self):
        """String describing Meta instance, variables, and attributes

        Returns
        -------
        out_str : str
            Nicely formatted output string

        """
        # Set the printing limits and get the label attributes
        ncol = 5
        lab_attrs = [mlab for mlab in dir(self) if not callable(mlab)]
        nlabels = len(lab_attrs)

        # Print the MetaLabels
        out_str = "MetaLabels:\n"
        out_str += "-----------\n"
        out_str += core_utils.fmt_output_in_cols(lab_atttrs, ncols=ncol,
                                                 max_num=nlabels)

        return out_str

    def default_values_from_type(self, val_type):
        """ Return the default values for each label based on their type

        Parameters
        ----------
        val_type : type
            Variable type for the value to be assigned to a MetaLabel

        Returns
        -------
        default_val : str, float, int, NoneType
            Sets NaN for all float values, -1 for all int values, and '' for
            all str values except for 'scale', which defaults to 'linear', and
            None for any othere data type

        """

        # Assign the default value
        if issubclass(val_type, str):
            default_val = ''
        elif isinstance(val_type, float):
            default_val = np.nan
        elif isinstance(val_type, int):
            default_val = -1
        else:
            default_val = None

        return default_val

    def default_values_from_attr(self, attr_name):
        """ Return the default values for each label based on their type

        Parameters
        ----------
        attr_name : str
            Label attribute name (e.g., max_val)

        Returns
        -------
        default_val : str, float, int, NoneType
            Sets NaN for all float values, -1 for all int values, and '' for
            all str values except for 'scale', which defaults to 'linear', and
            None for any othere data type

        Raises
        ------
        ValueError
            For unknown attr_name

        """

        # Test the input parameter
        if attr_name not in self.label_type.keys():
            raise ValueError('uknown label attribute {:}'.format(attr_name))

        # Assign the default value
        if attr_name == 'scale':
            default_val = 'linear'
        else:
            default_val = self.default_values_from_type(
                self.label_type[attr_name])

        return default_val

