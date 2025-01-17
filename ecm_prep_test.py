#!/usr/bin/env python3

""" Tests for running the measure preparation routine """

# Import code to be tested
import ecm_prep
# Import needed packages
import unittest
import numpy
import os
from collections import OrderedDict
import warnings
import copy
import itertools


class CommonMethods(object):
    """Define common methods for use in all tests below."""

    def dict_check(self, dict1, dict2):
        """Check the equality of two dicts.

        Args:
            dict1 (dict): First dictionary to be compared
            dict2 (dict): Second dictionary to be compared

        Raises:
            AssertionError: If dictionaries are not equal.
        """
        # zip() and zip_longest() produce tuples for the items
        # identified, where in the case of a dict, the first item
        # in the tuple is the key and the second item is the value;
        # in the case where the dicts are not of identical size,
        # zip_longest() will use the fill value created below as a
        # substitute in the dict that has missing content; this
        # value is given as a tuple to be of comparable structure
        # to the normal output from zip_longest()
        fill_val = ('substituted entry', 5.2)

        # In this structure, k and k2 are the keys that correspond to
        # the dicts or unitary values that are found in i and i2,
        # respectively, at the current level of the recursive
        # exploration of dict1 and dict2, respectively
        for (k, i), (k2, i2) in itertools.zip_longest(sorted(dict1.items()),
                                                      sorted(dict2.items()),
                                                      fillvalue=fill_val):

            # Confirm that at the current location in the dict structure,
            # the keys are equal; this should fail if one of the dicts
            # is empty, is missing section(s), or has different key names
            self.assertEqual(k, k2)

            # If the recursion has not yet reached the terminal/leaf node
            if isinstance(i, dict):
                # Test that the dicts from the current keys are equal
                self.assertCountEqual(i, i2)
                # Continue to recursively traverse the dict
                self.dict_check(i, i2)

            # At the terminal/leaf node
            else:
                # Compare the values, allowing for floating point inaccuracy
                self.assertAlmostEqual(dict1[k], dict2[k2], places=2)


class EPlusGlobalsTest(unittest.TestCase, CommonMethods):
    """Test 'find_vintage_weights' function.

    Ensure building vintage square footages are read in properly from a
    cbecs data file and that the proper weights are derived for mapping
    EnergyPlus building vintages to Scout's 'new' and 'retrofit' building
    structure types.

    Attributes:
        cbecs_sf_byvint (dict): Commercial square footage by vintage data.
        eplus_globals_ok (object): EPlusGlobals object with square footage and
            vintage weights attributes to test against expected outputs.
        eplus_failpath (string): Path to invalid EnergyPlus simulation data
            file that should cause EPlusGlobals object instantiation to fail.
        ok_out_weights (dict): Correct vintage weights output for
            'find_vintage_weights'function given valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables for use across all class functions."""
        base_dir = os.getcwd()
        cls.cbecs_sf_byvint = {
            '2004 to 2007': 6524.0, '1960 to 1969': 10362.0,
            '1946 to 1959': 7381.0, '1970 to 1979': 10846.0,
            '1990 to 1999': 13803.0, '2000 to 2003': 7215.0,
            'Before 1920': 3980.0, '2008 to 2012': 5726.0,
            '1920 to 1945': 6020.0, '1980 to 1989': 15185.0}
        cls.eplus_globals_ok = ecm_prep.EPlusGlobals(
            base_dir + "/ecm_definitions/energyplus_data/energyplus_test_ok",
            cls.cbecs_sf_byvint)
        cls.eplus_failpath = \
            base_dir + "/ecm_definitions/energyplus_data/energyplus_test_fail"
        cls.ok_out_weights = {
            'DOE Ref 1980-2004': 0.42, '90.1-2004': 0.07,
            '90.1-2010': 0.07, 'DOE Ref Pre-1980': 0.44,
            '90.1-2013': 1}

    def test_vintageweights(self):
        """Test find_vintage_weights function given valid inputs.

        Note:
            Ensure EnergyPlus building vintage type data are correctly weighted
            by their square footages (derived from CBECs data).

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(
            self.eplus_globals_ok.find_vintage_weights(),
            self.ok_out_weights)

    # Test that an error is raised when unexpected eplus vintages are present
    def test_vintageweights_fail(self):
        """Test find_vintage_weights function given invalid inputs.

        Note:
            Ensure that KeyError is raised when an unexpected EnergyPlus
            building vintage is present.

        Raises:
            AssertionError: If KeyError is not raised.
        """
        with self.assertRaises(KeyError):
            ecm_prep.EPlusGlobals(
                self.eplus_failpath,
                self.cbecs_sf_byvint).find_vintage_weights()


class EPlusUpdateTest(unittest.TestCase, CommonMethods):
    """Test the 'fill_eplus' function and its supporting functions.

    Ensure that the 'build_array' function properly assembles a set of input
    CSVs into a structured array and that the 'create_perf_dict' and
    'fill_perf_dict' functions properly initialize and fill a measure
    performance dictionary with results from an EnergyPlus simulation output
    file.

    Attributes:
        meas (object): Measure object instantiated based on sample_measure_in
            attributes.
        eplus_dir (string): EnergyPlus simulation output file directory.
        eplus_coltypes (list): List of expected EnergyPlus output data types.
        eplus_basecols (list): Variable columns that should never be removed.
        mseg_in (dict): Sample baseline microsegment stock/energy data.
        ok_eplus_vintagewts (dict): Sample EnergyPlus vintage weights.
        ok_eplusfiles_in (list): List of all EnergyPlus simulation file names.
        ok_perfarray_in (numpy recarray): Valid structured array of
            EnergyPlus-based relative savings data.
        fail_perfarray_in (numpy recarray): Invalid structured array of
            EnergyPlus-based relative savings data (missing certain climate
            zones, building types, and building vintages).
        fail_perfdictempty_in (dict): Invalid empty dictionary to fill with
            EnergyPlus-based performance information broken down by climate
            zone, building type/vintage, fuel type, and end use (dictionary
            includes invalid climate zone key).
        ok_array_type_out (string): The array type that should be yielded by
            'convert_to_array' given valid input.
        ok_array_length_out (int): The array length that should be yielded by
            'convert_to_array' given valid input.
        ok_array_names_out (tuple): Tuple of column names for the recarray that
            should be yielded by 'convert_to_array' given valid input.
        ok_perfdictempty_out (dict): The empty dictionary that should be
            yielded by 'create_perf_dict' given valid inputs.
        ok_perfdictfill_out (dict): The dictionary filled with EnergyPlus-based
            measure performance information that should be yielded by
            'fill_perf_dict' and 'fill_eplus' given valid inputs.

    Raises:
        AssertionError: If function yields unexpected results or does not
            raise a KeyError when it should.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Sample measure attributes to use in instantiating Measure object.
        sample_measure_in = OrderedDict([
            ("name", "eplus sample measure 1"),
            ("status", OrderedDict([
                ("active", 1), ("updated", 1)])),
            ("installed_cost", 25),
            ("cost_units", "2014$/unit"),
            ("energy_efficiency", OrderedDict([
                ("EnergyPlus file", "eplus_sample_measure")])),
            ("energy_efficiency_units", OrderedDict([
                ("primary", "relative savings (constant)"),
                ("secondary", "relative savings (constant)")])),
            ("energy_efficiency_source", None),
            ("market_entry_year", None),
            ("market_exit_year", None),
            ("product_lifetime", 10),
            ("structure_type", ["new", "retrofit"]),
            ("bldg_type", ["assembly", "education"]),
            ("climate_zone", ["hot dry", "mixed humid"]),
            ("fuel_type", OrderedDict([
                ("primary", ["electricity"]),
                ("secondary", [
                    "electricity", "natural gas", "distillate"])])),
            ("fuel_switch_to", None),
            ("end_use", OrderedDict([
                ("primary", ["lighting"]),
                ("secondary", ["heating", "cooling"])])),
            ("technology", OrderedDict([
                ("primary", [
                    "technology A", "technology B", "technology C"]),
                ("secondary", ["windows conduction", "windows solar"])]))])
        # Base directory
        base_dir = os.getcwd()
        # Useful global variables for the sample measure object
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        cls.meas = ecm_prep.Measure(handyvars, **sample_measure_in)
        # Finalize the measure's 'technology_type' attribute (handled by the
        # 'fill_attr' function, which is not run as part of this test)
        cls.meas.technology_type = {"primary": "supply", "secondary": "demand"}
        cls.eplus_dir = \
            base_dir + "/ecm_definitions/energyplus_data/energyplus_test_ok"
        cls.eplus_coltypes = [
            ('building_type', '<U50'), ('climate_zone', '<U50'),
            ('template', '<U50'), ('measure', '<U50'), ('status', '<U50'),
            ('ep_version', '<U50'), ('os_version', '<U50'),
            ('timestamp', '<U50'), ('cooling_electricity', '<f8'),
            ('cooling_water', '<f8'), ('district_chilled_water', '<f8'),
            ('district_hot_water_heating', '<f8'),
            ('district_hot_water_service_hot_water', '<f8'),
            ('exterior_equipment_electricity', '<f8'),
            ('exterior_equipment_gas', '<f8'),
            ('exterior_equipment_other_fuel', '<f8'),
            ('exterior_equipment_water', '<f8'),
            ('exterior_lighting_electricity', '<f8'),
            ('fan_electricity', '<f8'),
            ('floor_area', '<f8'), ('generated_electricity', '<f8'),
            ('heat_recovery_electricity', '<f8'),
            ('heat_rejection_electricity', '<f8'),
            ('heating_electricity', '<f8'), ('heating_gas', '<f8'),
            ('heating_other_fuel', '<f8'), ('heating_water', '<f8'),
            ('humidification_electricity', '<f8'),
            ('humidification_water', '<f8'),
            ('interior_equipment_electricity', '<f8'),
            ('interior_equipment_gas', '<f8'),
            ('interior_equipment_other_fuel', '<f8'),
            ('interior_equipment_water', '<f8'),
            ('interior_lighting_electricity', '<f8'),
            ('net_site_electricity', '<f8'), ('net_water', '<f8'),
            ('pump_electricity', '<f8'),
            ('refrigeration_electricity', '<f8'),
            ('service_water', '<f8'),
            ('service_water_heating_electricity', '<f8'),
            ('service_water_heating_gas', '<f8'),
            ('service_water_heating_other_fuel', '<f8'), ('total_gas', '<f8'),
            ('total_other_fuel', '<f8'), ('total_site_electricity', '<f8'),
            ('total_water', '<f8')]
        cls.eplus_basecols = [
            'building_type', 'climate_zone', 'template', 'measure']
        cls.mseg_in = {
            'hot dry': {
                'education': {
                    'electricity': {
                        'lighting': {
                            "technology A": 0,
                            "technology B": 0,
                            "technology C": 0},
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'natural gas': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'distillate': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}}},
                'assembly': {
                    'electricity': {
                        'lighting': {
                            "technology A": 0,
                            "technology B": 0,
                            "technology C": 0},
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'natural gas': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'distillate': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}}}},
            'mixed humid': {
                'education': {
                    'electricity': {
                        'lighting': {
                            "technology A": 0,
                            "technology B": 0,
                            "technology C": 0},
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'natural gas': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'distillate': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}}},
                'assembly': {
                    'electricity': {
                        'lighting': {
                            "technology A": 0,
                            "technology B": 0,
                            "technology C": 0},
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'ASHP': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'natural gas': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}},
                        'cooling': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}},
                    'distillate': {
                        'heating': {
                            'supply': {
                                'technology A': 0},
                            'demand': {
                                'windows conduction': 0,
                                'windows solar': 0}}}}}}
        # Set EnergyPlus building vintage weights (based on square footage)
        cls.ok_eplus_vintagewts = {
            'DOE Ref Pre-1980': 0.44, '90.1-2004': 0.07, '90.1-2010': 0.07,
            '90.1-2013': 1, 'DOE Ref 1980-2004': 0.42}
        cls.ok_eplusfiles_in = [
            "fullservicerestaurant_scout_2016-07-23-16-25-59.csv",
            "secondaryschool_scout_2016-07-23-16-25-59.csv",
            "primaryschool_scout_2016-07-23-16-25-59.csv",
            "smallhotel_scout_2016-07-23-16-25-59.csv",
            "hospital_scout_2016-07-23-16-25-59.csv"]
        # Set full paths for EnergyPlus files that are relevant to the measure
        eplusfiles_in_fullpaths = [cls.eplus_dir + '/' + x for x in [
            "secondaryschool_scout_2016-07-23-16-25-59.csv",
            "primaryschool_scout_2016-07-23-16-25-59.csv",
            "hospital_scout_2016-07-23-16-25-59.csv"]]
        # Use 'build_array' to generate test input data for 'fill_eplus'
        cls.ok_perfarray_in = cls.meas.build_array(
            cls.eplus_coltypes, eplusfiles_in_fullpaths)
        cls.fail_perfarray_in = numpy.rec.array([
            ('BA-MixedHumid', 'SecondarySchool', '90.1-2013', 'Success',
             0, 0.5, 0.5, 0.25, 0.25, 0, 0.25, 0.75, 0, -0.1, 0.1, 0.5, -0.2),
            ('BA-HotDry', 'PrimarySchool', 'DOE Ref 1980-2004', 'Success',
             0, 0.5, 0.5, 0.25, 0.25, 0, 0.25, 0.75, 0, -0.1, 0.1, 0.5, -0.2)],
            dtype=[('climate_zone', '<U13'), ('building_type', '<U22'),
                   ('template', '<U17'), ('status', 'U7'),
                   ('floor_area', '<f8'),
                   ('total_site_electricity', '<f8'),
                   ('net_site_electricity', '<f8'),
                   ('total_gas', '<f8'), ('total_other_fuel', '<f8'),
                   ('total_water', '<f8'), ('net_water', '<f8'),
                   ('interior_lighting_electricity', '<f8'),
                   ('interior_equipment_electricity', '<f8'),
                   ('heating_electricity', '<f8'),
                   ('cooling_electricity', '<f8'),
                   ('heating_gas', '<f8'),
                   ('heat_recovery_electricity', '<f8')])
        cls.fail_perfdictempty_in = {
            "primary": {
                'blazing hot': {
                    'education': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}}},
                'mixed humid': {
                    'education': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}}}},
            "secondary": {
                'blazing hot': {
                    'education': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}}}},
                'mixed humid': {
                    'education': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}}}}}}
        cls.ok_array_length_out = 240
        cls.ok_arraynames_out = cls.ok_perfarray_in.dtype.names
        cls.ok_perfdictempty_out = {
            "primary": {
                'hot dry': {
                    'education': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}}},
                'mixed humid': {
                    'education': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'lighting': {'retrofit': 0, 'new': 0}}}}},
            "secondary": {
                'hot dry': {
                    'education': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}}},
                'mixed humid': {
                    'education': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0, 'new': 0}},
                        'natural gas': {
                            'heating': {'retrofit': 0, 'new': 0}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}}}}}
        cls.ok_perfdictfill_out = {
            "primary": {
                'hot dry': {
                    'education': {
                        'electricity': {
                            'lighting': {'retrofit': 0.5, 'new': 0.5}}},
                    'assembly': {
                        'electricity': {
                            'lighting': {'retrofit': 0.5, 'new': 0.5}}}},
                'mixed humid': {
                    'education': {
                        'electricity': {
                            'lighting': {
                                'retrofit': 0.75, 'new': 0.935}}},
                    'assembly': {
                        'electricity': {
                            'lighting': {
                                'retrofit': 0.75, 'new': 1}}}}},
            "secondary": {
                'hot dry': {
                    'education': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0.75, 'new': 0.555}},
                        'natural gas': {
                            'heating': {
                                'retrofit': 1.25, 'new': 1.25}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0.75, 'new': 0.75}},
                        'natural gas': {
                            'heating': {
                                'retrofit': 1.25, 'new': 1.25}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}}},
                'mixed humid': {
                    'education': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0.5, 'new': 0.87}},
                        'natural gas': {
                            'heating': {
                                'retrofit': 1.5, 'new': 1.13}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}},
                    'assembly': {
                        'electricity': {
                            'heating': {'retrofit': 0, 'new': 0},
                            'cooling': {'retrofit': 0.5, 'new': 1}},
                        'natural gas': {
                            'heating': {
                                'retrofit': 1.5, 'new': 1}},
                        'distillate': {
                            'heating': {'retrofit': 0, 'new': 0}}}}}}

    def test_array_build(self):
        """Test 'build_array' function given valid inputs.

        Note:
            Ensure correct assembly of numpy arrays from all EnergyPlus
            files that are relevant to a test measure.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Check for correct column names and length of the converted array
        self.assertEqual(
            [self.ok_perfarray_in.dtype.names, len(self.ok_perfarray_in)],
            [self.ok_arraynames_out, self.ok_array_length_out])

    def test_dict_creation(self):
        """Test 'create_perf_dict' function given valid inputs.

        Note:
            Ensure correct generation of measure performance dictionary.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(self.meas.create_perf_dict(
            self.mseg_in), self.ok_perfdictempty_out)

    def test_dict_fill(self):
        """Test 'fill_perf_dict' function given valid inputs.

        Note:
            Ensure correct updating of measure performance dictionary
            with EnergyPlus simulation results.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(
            self.meas.fill_perf_dict(
                self.ok_perfdictempty_out, self.ok_perfarray_in,
                self.ok_eplus_vintagewts, self.eplus_basecols,
                eplus_bldg_types={}),
            self.ok_perfdictfill_out)

    def test_dict_fill_fail(self):
        """Test 'fill_perf_dict' function given invalid inputs.

        Note:
            Ensure function fails when given either invalid blank
            performance dictionary to fill or invalid input array of
            EnergyPlus simulation information to fill the dict with.

        Raises:
            AssertionError: If KeyError is not raised
        """
        with self.assertRaises(KeyError):
            # Case with invalid input dictionary
            self.meas.fill_perf_dict(
                self.fail_perfdictempty_in, self.ok_perfarray_in,
                self.ok_eplus_vintagewts, self.eplus_basecols,
                eplus_bldg_types={})
            # Case with incomplete input array of EnergyPlus information
            self.meas.fill_perf_dict(
                self.ok_perfdictempty_out, self.fail_perfarray_in,
                self.ok_eplus_vintagewts, self.eplus_basecols,
                eplus_bldg_types={})

    def test_fill_eplus(self):
        """Test 'fill_eplus' function given valid inputs.

        Note:
            Ensure proper updating of measure performance with
            EnergyPlus simulation results from start ('convert_to_array')
            to finish ('fill_perf_dict').

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.meas.fill_eplus(
            self.mseg_in, self.eplus_dir, self.eplus_coltypes,
            self.ok_eplusfiles_in, self.ok_eplus_vintagewts,
            self.eplus_basecols)
        # Check for properly updated measure energy_efficiency,
        # energy_efficiency_source, and energy_efficiency_source_quality
        # attributes.
        self.dict_check(
            self.meas.energy_efficiency, self.ok_perfdictfill_out)
        self.assertEqual(
            self.meas.energy_efficiency_source, 'EnergyPlus/OpenStudio')


class MarketUpdatesTest(unittest.TestCase, CommonMethods):
    """Test 'fill_mkts' function.

    Ensure that the function properly fills in market microsegment data
    for a series of sample measures.

    Attributes:
        verbose (NoneType): Determines whether to print all user messages.
        convert_data (dict): ECM cost conversion data.
        sample_mseg_in (dict): Sample baseline microsegment stock/energy.
        sample_cpl_in (dict): Sample baseline technology cost, performance,
            and lifetime.
        ok_tpmeas_fullchk_in (list): Valid sample measure information
            to update with markets data; measure cost, performance, and life
            attributes are given as point estimates. Used to check the full
            measure 'markets' attribute under a 'Technical potential scenario.
        ok_tpmeas_partchk_in (list): Valid sample measure information to update
            with markets data; measure cost, performance, and lifetime
            attributes are given as point estimates. Used to check the
            'master_mseg' branch of measure 'markets' attribute under a
            'Technical potential scenario.
        ok_mapmeas_partchk_in (list): Valid sample measure information
            to update with markets data; measure cost, performance, and life
            attributes are given as point estimates. Used to check the
            'master_mseg' branch of measure 'markets' attribute under a 'Max
            adoption potential scenario.
        ok_distmeas_in (list): Valid sample measure information to
            update with markets data; measure cost, performance, and lifetime
            attributes are given as probability distributions.
        ok_partialmeas_in (list): Partially valid measure information to update
            with markets data.
        failmeas_in (list): Invalid sample measure information that should
            yield error when entered into function.
        warnmeas_in (list): Incomplete sample measure information that
            should yield warnings when entered into function (measure
            sub-market scaling fraction source attributions are invalid).
        ok_tpmeas_fullchk_msegout (list): Master market microsegments
            information that should be yielded given 'ok_tpmeas_fullchk_in'.
        ok_tpmeas_fullchk_competechoiceout (list): Consumer choice information
            that should be yielded given 'ok_tpmeas_fullchk_in'.
        ok_tpmeas_fullchk_msegadjout (list): Secondary microsegment adjustment
            information that should be yielded given 'ok_tpmeas_fullchk_in'.
        ok_tpmeas_fullchk_break_out (list): Output breakout information that
            should be yielded given 'ok_tpmeas_fullchk_in'.
        ok_tpmeas_partchk_msegout (list): Master market microsegments
            information that should be yielded given 'ok_tpmeas_partchk_in'.
        ok_mapmas_partchck_msegout (list): Master market microsegments
            information that should be yielded given 'ok_mapmeas_partchk_in'.
        ok_distmeas_out (list): Means and sampling Ns for measure energy/cost
            markets and lifetime that should be yielded given 'ok_distmeas_in'.
        ok_partialmeas_out (list): Master market microsegments information
            that should be yielded given 'ok_partialmeas_in'.
        ok_warnmeas_out (list): Warning messages that should be yielded
            given 'warnmeas_in'.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        # Hard code aeo_years to fit test years
        handyvars.aeo_years = ["2009", "2010"]
        handyvars.retro_rate = 0.02
        # Hard code carbon intensity, site-source conversion, and cost data for
        # tests such that these data are not dependent on an input file that
        # may change in the future
        handyvars.ss_conv = {
            "electricity": {"2009": 3.19, "2010": 3.20},
            "natural gas": {"2009": 1.01, "2010": 1.01},
            "distillate": {"2009": 1.01, "2010": 1.01},
            "other fuel": {"2009": 1.01, "2010": 1.01}}
        handyvars.carb_int = {
            "residential": {
                "electricity": {"2009": 56.84702689, "2010": 56.16823191},
                "natural gas": {"2009": 56.51576602, "2010": 54.91762852},
                "distillate": {"2009": 49.5454521, "2010": 52.59751597},
                "other fuel": {"2009": 49.5454521, "2010": 52.59751597}},
            "commercial": {
                "electricity": {"2009": 56.84702689, "2010": 56.16823191},
                "natural gas": {"2009": 56.51576602, "2010": 54.91762852},
                "distillate": {"2009": 49.5454521, "2010": 52.59751597},
                "other fuel": {"2009": 49.5454521, "2010": 52.59751597}}}
        handyvars.ecosts = {
            "residential": {
                "electricity": {"2009": 10.14, "2010": 9.67},
                "natural gas": {"2009": 11.28, "2010": 10.78},
                "distillate": {"2009": 21.23, "2010": 20.59},
                "other fuel": {"2009": 21.23, "2010": 20.59}},
            "commercial": {
                "electricity": {"2009": 9.08, "2010": 8.55},
                "natural gas": {"2009": 8.96, "2010": 8.59},
                "distillate": {"2009": 14.81, "2010": 14.87},
                "other fuel": {"2009": 14.81, "2010": 14.87}}}
        handyvars.ccosts = {"2009": 33, "2010": 33}
        cls.verbose = None
        cls.convert_data = {}
        cls.sample_mseg_in = {
            "AIA_CZ1": {
                "assembly": {
                    "total square footage": {"2009": 11, "2010": 11},
                    "new square footage": {"2009": 0, "2010": 0},
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 0, "2010": 0}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 1, "2010": 1}},
                                "lighting gain": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": -7, "2010": -7}}}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 5, "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 6, "2010": 6}},
                                "lighting gain": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 6, "2010": 6}}}},
                        "lighting": {
                            "T5 F28": {
                                "stock": "NA",
                                "energy": {
                                    "2009": 11, "2010": 11}}},
                        "PCs": {
                            "stock": "NA",
                            "energy": {"2009": 12, "2010": 12}},
                        "MELs": {
                            "distribution transformers": {
                                "stock": "NA",
                                "energy": {"2009": 24, "2010": 24}
                            }
                        }}},
                "single family home": {
                    "total square footage": {"2009": 100, "2010": 200},
                    "total homes": {"2009": 1000, "2010": 1000},
                    "new homes": {"2009": 100, "2010": 50},
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 0, "2010": 0}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 1, "2010": 1}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {"2009": 10, "2010": 10}}},
                            "supply": {
                                "resistance heat": {
                                    "stock": {"2009": 2, "2010": 2},
                                    "energy": {"2009": 2, "2010": 2}},
                                "ASHP": {
                                    "stock": {"2009": 3, "2010": 3},
                                    "energy": {"2009": 3, "2010": 3}},
                                "GSHP": {
                                    "stock": {"2009": 4, "2010": 4},
                                    "energy": {"2009": 4, "2010": 4}}}},
                        "secondary heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 5, "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 6, "2010": 6}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {"2009": 10, "2010": 10}}},
                            "supply": {"non-specific": 7}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 5, "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 6, "2010": 6}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {"2009": 10, "2010": 10}}},
                            "supply": {
                                "central AC": {
                                    "stock": {"2009": 7, "2010": 7},
                                    "energy": {"2009": 7, "2010": 7}},
                                "room AC": {
                                    "stock": {"2009": 8, "2010": 8},
                                    "energy": {"2009": 8, "2010": 8}},
                                "ASHP": {
                                    "stock": {"2009": 9, "2010": 9},
                                    "energy": {"2009": 9, "2010": 9}},
                                "GSHP": {
                                    "stock": {"2009": 10, "2010": 10},
                                    "energy": {"2009": 10, "2010": 10}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                "stock": {"2009": 11, "2010": 11},
                                "energy": {"2009": 11, "2010": 11}},
                            "general service (LED)": {
                                "stock": {"2009": 12, "2010": 12},
                                "energy": {"2009": 12, "2010": 12}},
                            "reflector (LED)": {
                                "stock": {"2009": 13, "2010": 13},
                                "energy": {"2009": 13, "2010": 13}},
                            "external (LED)": {
                                "stock": {"2009": 14, "2010": 14},
                                "energy": {"2009": 14, "2010": 14}}},
                        "refrigeration": {
                            "stock": {"2009": 111, "2010": 111},
                            "energy": {"2009": 111, "2010": 111}},
                        "TVs": {
                            "TVs": {
                                "stock": {"2009": 99, "2010": 99},
                                "energy": {"2009": 9, "2010": 9}},
                            "set top box": {
                                "stock": {"2009": 99, "2010": 99},
                                "energy": {"2009": 999, "2010": 999}}
                            },
                        "computers": {
                            "desktop PC": {
                                "stock": {"2009": 44, "2010": 44},
                                "energy": {"2009": 4, "2010": 4}},
                            "laptop PC": {
                                "stock": {"2009": 55, "2010": 55},
                                "energy": {"2009": 5, "2010": 5}}
                            },
                        "other (grid electric)": {
                            "freezers": {
                                "stock": {"2009": 222, "2010": 222},
                                "energy": {"2009": 222, "2010": 222}},
                            "other MELs": {
                                "stock": {"2009": 333, "2010": 333},
                                "energy": {"2009": 333, "2010": 333}}}},
                    "natural gas": {
                        "water heating": {
                            "stock": {"2009": 15, "2010": 15},
                            "energy": {"2009": 15, "2010": 15}},
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 0,
                                               "2010": 0}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 1,
                                               "2010": 1}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 10, "2010": 10}}}},
                        "secondary heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 5,
                                               "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 6,
                                               "2010": 6}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 10, "2010": 10}}}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 5, "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 6, "2010": 6}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {
                                        "2009": 10, "2010": 10}}}}}},
                "multi family home": {
                    "total square footage": {"2009": 300, "2010": 400},
                    "total homes": {"2009": 1000, "2010": 1000},
                    "new homes": {"2009": 100, "2010": 50},
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 0, "2010": 0}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 1, "2010": 1}}},
                            "supply": {
                                "resistance heat": {
                                    "stock": {"2009": 2, "2010": 2},
                                    "energy": {"2009": 2, "2010": 2}},
                                "ASHP": {
                                    "stock": {"2009": 3, "2010": 3},
                                    "energy": {"2009": 3, "2010": 3}},
                                "GSHP": {
                                    "stock": {"2009": 4, "2010": 4},
                                    "energy": {"2009": 4, "2010": 4}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                "stock": {"2009": 11, "2010": 11},
                                "energy": {"2009": 11, "2010": 11}},
                            "general service (LED)": {
                                "stock": {"2009": 12, "2010": 12},
                                "energy": {"2009": 12, "2010": 12}},
                            "reflector (LED)": {
                                "stock": {"2009": 13, "2010": 13},
                                "energy": {"2009": 13, "2010": 13}},
                            "external (LED)": {
                                "stock": {"2009": 14, "2010": 14},
                                "energy": {"2009": 14, "2010": 14}}}}}},
            "AIA_CZ2": {
                "single family home": {
                    "total square footage": {"2009": 500, "2010": 600},
                    "total homes": {"2009": 1000, "2010": 1000},
                    "new homes": {"2009": 100, "2010": 50},
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 0, "2010": 0}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 1, "2010": 1}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {"2009": 10, "2010": 10}}},
                            "supply": {
                                "resistance heat": {
                                    "stock": {"2009": 2, "2010": 2},
                                    "energy": {"2009": 2, "2010": 2}},
                                "ASHP": {
                                    "stock": {"2009": 3, "2010": 3},
                                    "energy": {"2009": 3, "2010": 3}},
                                "GSHP": {
                                    "stock": {"2009": 4, "2010": 4},
                                    "energy": {"2009": 4, "2010": 4}}}},
                        "secondary heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 5, "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 6, "2010": 6}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {"2009": 10, "2010": 10}}},
                            "supply": {"non-specific": 7}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 5, "2010": 5}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 6, "2010": 6}},
                                "infiltration": {
                                    "stock": "NA",
                                    "energy": {"2009": 10, "2010": 10}}},
                            "supply": {
                                "central AC": {
                                    "stock": {"2009": 7, "2010": 7},
                                    "energy": {"2009": 7, "2010": 7}},
                                "room AC": {
                                    "stock": {"2009": 8, "2010": 8},
                                    "energy": {"2009": 8, "2010": 8}},
                                "ASHP": {
                                    "stock": {"2009": 9, "2010": 9},
                                    "energy": {"2009": 9, "2010": 9}},
                                "GSHP": {
                                    "stock": {"2009": 10, "2010": 10},
                                    "energy": {"2009": 10, "2010": 10}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                "stock": {"2009": 11, "2010": 11},
                                "energy": {"2009": 11, "2010": 11}},
                            "general service (LED)": {
                                "stock": {"2009": 12, "2010": 12},
                                "energy": {"2009": 12, "2010": 12}},
                            "reflector (LED)": {
                                "stock": {"2009": 13, "2010": 13},
                                "energy": {"2009": 13, "2010": 13}},
                            "external (LED)": {
                                "stock": {"2009": 14, "2010": 14},
                                "energy": {"2009": 14, "2010": 14}}},
                        "TVs": {
                            "TVs": {
                                "stock": {"2009": 99, "2010": 99},
                                "energy": {"2009": 9, "2010": 9}},
                            "set top box": {
                                "stock": {"2009": 99, "2010": 99},
                                "energy": {"2009": 999, "2010": 999}}
                            },
                        "computers": {
                            "desktop PC": {
                                "stock": {"2009": 44, "2010": 44},
                                "energy": {"2009": 4, "2010": 4}},
                            "laptop PC": {
                                "stock": {"2009": 55, "2010": 55},
                                "energy": {"2009": 5, "2010": 5}}
                            }},
                    "natural gas": {"water heating": {
                                    "stock": {"2009": 15, "2010": 15},
                                    "energy": {"2009": 15, "2010": 15}}}},
                "multi family home": {
                    "total square footage": {"2009": 700, "2010": 800},
                    "total homes": {"2009": 1000, "2010": 1000},
                    "new homes": {"2009": 100, "2010": 50},
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "stock": "NA",
                                    "energy": {"2009": 0, "2010": 0}},
                                "windows solar": {
                                    "stock": "NA",
                                    "energy": {"2009": 1, "2010": 1}}},
                            "supply": {
                                "resistance heat": {
                                    "stock": {"2009": 2, "2010": 2},
                                    "energy": {"2009": 2, "2010": 2}},
                                "ASHP": {
                                    "stock": {"2009": 3, "2010": 3},
                                    "energy": {"2009": 3, "2010": 3}},
                                "GSHP": {
                                    "stock": {"2009": 4, "2010": 4}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                "stock": {"2009": 11, "2010": 11},
                                "energy": {"2009": 11, "2010": 11}},
                            "general service (LED)": {
                                "stock": {"2009": 12, "2010": 12},
                                "energy": {"2009": 12, "2010": 12}},
                            "reflector (LED)": {
                                "stock": {"2009": 13, "2010": 13},
                                "energy": {"2009": 13, "2010": 13}},
                            "external (LED)": {
                                "stock": {"2009": 14, "2010": 14},
                                "energy": {"2009": 14, "2010": 14}}}}}},
            "AIA_CZ4": {
                "multi family home": {
                    "total square footage": {"2009": 900, "2010": 1000},
                    "total homes": {"2009": 1000, "2010": 1000},
                    "new homes": {"2009": 100, "2010": 50},
                    "electricity": {
                        "lighting": {
                            "linear fluorescent (LED)": {
                                "stock": {"2009": 11, "2010": 11},
                                "energy": {"2009": 11, "2010": 11}},
                            "general service (LED)": {
                                "stock": {"2009": 12, "2010": 12},
                                "energy": {"2009": 12, "2010": 12}},
                            "reflector (LED)": {
                                "stock": {"2009": 13, "2010": 13},
                                "energy": {"2009": 13, "2010": 13}},
                            "external (LED)": {
                                "stock": {"2009": 14, "2010": 14},
                                "energy": {"2009": 14, "2010": 14}}}}}}}
        cls.sample_cpl_in = {
            "AIA_CZ1": {
                "assembly": {
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 10, "2010": 10},
                                        "range": {"2009": 1, "2010": 1},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "lighting gain": 0}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 10, "2010": 10},
                                        "range": {"2009": 1, "2010": 1},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "lighting gain": 0}},
                        "lighting": {
                            "T5 F28": {
                                "performance": {
                                    "typical": {"2009": 14, "2010": 14},
                                    "best": {"2009": 14, "2010": 14},
                                    "units": "lm/W",
                                    "source":
                                    "EIA AEO"},
                                "installed cost": {
                                    "typical": {"2009": 14, "2010": 14},
                                    "best": {"2009": 14, "2010": 14},
                                    "units": "2014$/ft^2 floor",
                                    "source": "EIA AEO"},
                                "lifetime": {
                                    "average": {"2009": 140, "2010": 140},
                                    "range": {"2009": 14, "2010": 14},
                                    "units": "years",
                                    "source": "EIA AEO"},
                                "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                        "PCs": 0,
                        "MELs": {
                            "distribution transformers": 0
                        }}},
                "single family home": {
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 10, "2010": 10},
                                        "range": {"2009": 1, "2010": 1},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "resistance heat": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "ASHP": {
                                    "performance": {
                                        "typical": {"2009": 3, "2010": 3},
                                        "best": {"2009": 3, "2010": 3},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 3, "2010": 3},
                                        "best": {"2009": 3, "2010": 3},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 30, "2010": 30},
                                        "range": {"2009": 3, "2010": 3},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "GSHP": {
                                    "performance": {
                                        "typical": {"2009": 4, "2010": 4},
                                        "best": {"2009": 4, "2010": 4},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 4, "2010": 4},
                                        "best": {"2009": 4, "2010": 4},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 40, "2010": 40},
                                        "range": {"2009": 4, "2010": 4},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "secondary heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 5, "2010": 5},
                                        "best": {"2009": 5, "2010": 5},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 5, "2010": 5},
                                        "best": {"2009": 5, "2010": 5},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 50, "2010": 50},
                                        "range": {"2009": 5, "2010": 5},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 6, "2010": 6},
                                        "best": {"2009": 6, "2010": 6},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 6, "2010": 6},
                                        "best": {"2009": 6, "2010": 6},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 60, "2010": 60},
                                        "range": {"2009": 6, "2010": 6},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "non-specific": {
                                    "performance": {
                                        "typical": {"2009": 7, "2010": 7},
                                        "best": {"2009": 7, "2010": 7},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 7, "2010": 7},
                                        "best": {"2009": 7, "2010": 7},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 70, "2010": 70},
                                        "range": {"2009": 7, "2010": 7},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {
                                            "new": {"2009": 8, "2010": 8},
                                            "existing": {
                                                "2009": 8, "2010": 8}
                                            },
                                        "best": {"2009": 8, "2010": 8},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 8, "2010": 8},
                                        "best": {"2009": 8, "2010": 8},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 80, "2010": 80},
                                        "range": {"2009": 8, "2010": 8},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 9, "2010": 9},
                                        "best": {"2009": 9, "2010": 9},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 9, "2010": 9},
                                        "best": {"2009": 9, "2010": 9},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 90, "2010": 90},
                                        "range": {"2009": 9, "2010": 9},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "central AC": {
                                    "performance": {
                                        "typical": {"2009": 10, "2010": 10},
                                        "best": {"2009": 10, "2010": 10},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 10, "2010": 10},
                                        "best": {"2009": 10, "2010": 10},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 100, "2010": 100},
                                        "range": {"2009": 10, "2010": 10},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "room AC": {
                                    "performance": {
                                        "typical": {"2009": 11, "2010": 11},
                                        "best": {"2009": 11, "2010": 11},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 11, "2010": 11},
                                        "best": {"2009": 11, "2010": 11},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 110, "2010": 110},
                                        "range": {"2009": 11, "2010": 11},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "ASHP": {
                                    "performance": {
                                        "typical": {"2009": 12, "2010": 12},
                                        "best": {"2009": 12, "2010": 12},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 12, "2010": 12},
                                        "best": {"2009": 12, "2010": 12},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 120, "2010": 120},
                                        "range": {"2009": 12, "2010": 12},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "GSHP": {
                                    "performance": {
                                        "typical": {"2009": 13, "2010": 13},
                                        "best": {"2009": 13, "2010": 13},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 13, "2010": 13},
                                        "best": {"2009": 13, "2010": 13},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 130, "2010": 130},
                                        "range": {"2009": 13, "2010": 13},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                    "performance": {
                                        "typical": {"2009": 14, "2010": 14},
                                        "best": {"2009": 14, "2010": 14},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 14, "2010": 14},
                                        "best": {"2009": 14, "2010": 14},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 140 * (3/24),
                                            "2010": 140 * (3/24)},
                                        "range": {"2009": 14, "2010": 14},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "general service (LED)": {
                                    "performance": {
                                        "typical": {"2009": 15, "2010": 15},
                                        "best": {"2009": 15, "2010": 15},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 15, "2010": 15},
                                        "best": {"2009": 15, "2010": 15},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 150 * (3/24),
                                            "2010": 150 * (3/24)},
                                        "range": {"2009": 15, "2010": 15},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "reflector (LED)": {
                                    "performance": {
                                        "typical": {"2009": 16, "2010": 16},
                                        "best": {"2009": 16, "2010": 16},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 16, "2010": 16},
                                        "best": {"2009": 16, "2010": 16},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 160 * (3/24),
                                            "2010": 160 * (3/24)},
                                        "range": {"2009": 16, "2010": 16},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "external (LED)": {
                                    "performance": {
                                        "typical": {"2009": 17, "2010": 17},
                                        "best": {"2009": 17, "2010": 17},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 17, "2010": 17},
                                        "best": {"2009": 17, "2010": 17},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 170 * (3/24),
                                            "2010": 170 * (3/24)},
                                        "range": {"2009": 17, "2010": 17},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                        "refrigeration": {
                            "performance": {
                                "typical": {"2009": 550, "2010": 550},
                                "best": {"2009": 450, "2010": 450},
                                "units": "kWh/yr",
                                "source":
                                "EIA AEO"},
                            "installed cost": {
                                "typical": {"2009": 300, "2010": 300},
                                "best": {"2009": 600, "2010": 600},
                                "units": "2010$/unit",
                                "source": "EIA AEO"},
                            "lifetime": {
                                "average": {"2009": 17, "2010": 17},
                                "range": {"2009": 6, "2010": 6},
                                "units": "years",
                                "source": "EIA AEO"},
                            "consumer choice": {
                                "competed market share": {
                                    "source": "EIA AEO",
                                    "model type": "logistic regression",
                                    "parameters": {
                                        "b1": {"2009": "NA", "2010": "NA"},
                                        "b2": {"2009": "NA",
                                               "2010": "NA"}}},
                                "competed market": {
                                    "source": "COBAM",
                                    "model type": "bass diffusion",
                                    "parameters": {
                                        "p": "NA",
                                        "q": "NA"}}}},
                        "TVs": {
                            "TVs": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}},
                            "set top box": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}}
                            },
                        "computers": {
                            "desktop PC": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}},
                            "laptop PC": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}}
                            },
                        "other (grid electric)": {
                            "freezers": {
                                "performance": {
                                    "typical": {"2009": 550, "2010": 550},
                                    "best": {"2009": 450, "2010": 450},
                                    "units": "kWh/yr",
                                    "source":
                                    "EIA AEO"},
                                "installed cost": {
                                    "typical": {"2009": 100, "2010": 100},
                                    "best": {"2009": 200, "2010": 200},
                                    "units": "2014$/unit",
                                    "source": "EIA AEO"},
                                "lifetime": {
                                    "average": {"2009": 15, "2010": 15},
                                    "range": {"2009": 3, "2010": 3},
                                    "units": "years",
                                    "source": "EIA AEO"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}},
                            "other MELs": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}}}},
                    "natural gas": {
                        "water heating": {
                            "performance": {
                                "typical": {"2009": 18, "2010": 18},
                                "best": {"2009": 18, "2010": 18},
                                "units": "EF",
                                "source":
                                "EIA AEO"},
                            "installed cost": {
                                "typical": {"2009": 18, "2010": 18},
                                "best": {"2009": 18, "2010": 18},
                                "units": "2014$/unit",
                                "source": "EIA AEO"},
                            "lifetime": {
                                "average": {"2009": 180, "2010": 180},
                                "range": {"2009": 18, "2010": 18},
                                "units": "years",
                                "source": "EIA AEO"},
                            "consumer choice": {
                                "competed market share": {
                                    "source": "EIA AEO",
                                    "model type": "logistic regression",
                                    "parameters": {
                                        "b1": {"2009": "NA", "2010": "NA"},
                                        "b2": {"2009": "NA",
                                               "2010": "NA"}}},
                                "competed market": {
                                    "source": "COBAM",
                                    "model type": "bass diffusion",
                                    "parameters": {
                                        "p": "NA",
                                        "q": "NA"}}}},
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 10, "2010": 10},
                                        "range": {"2009": 1, "2010": 1},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "secondary heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 5, "2010": 5},
                                        "best": {"2009": 5, "2010": 5},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 5, "2010": 5},
                                        "best": {"2009": 5, "2010": 5},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 50, "2010": 50},
                                        "range": {"2009": 5, "2010": 5},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 6, "2010": 6},
                                        "best": {"2009": 6, "2010": 6},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 6, "2010": 6},
                                        "best": {"2009": 6, "2010": 6},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 60, "2010": 60},
                                        "range": {"2009": 6, "2010": 6},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 8, "2010": 8},
                                        "best": {"2009": 8, "2010": 8},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 8, "2010": 8},
                                        "best": {"2009": 8, "2010": 8},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 80, "2010": 80},
                                        "range": {"2009": 8, "2010": 8},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 9, "2010": 9},
                                        "best": {"2009": 9, "2010": 9},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 9, "2010": 9},
                                        "best": {"2009": 9, "2010": 9},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 90, "2010": 90},
                                        "range": {"2009": 9, "2010": 9},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}}}},
                "multi family home": {
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 19, "2010": 19},
                                        "best": {"2009": 19, "2010": 19},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 19, "2010": 19},
                                        "best": {"2009": 19, "2010": 19},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 190, "2010": 190},
                                        "range": {"2009": 19, "2010": 19},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 20, "2010": 20},
                                        "best": {"2009": 20, "2010": 20},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 20, "2010": 20},
                                        "best": {"2009": 20, "2010": 20},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 200, "2010": 200},
                                        "range": {"2009": 20, "2010": 20},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "resistance heat": {
                                    "performance": {
                                        "typical": {"2009": 21, "2010": 21},
                                        "best": {"2009": 21, "2010": 21},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 21, "2010": 21},
                                        "best": {"2009": 21, "2010": 21},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 210, "2010": 210},
                                        "range": {"2009": 21, "2010": 21},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "ASHP": {
                                    "performance": {
                                        "typical": {"2009": 22, "2010": 22},
                                        "best": {"2009": 22, "2010": 22},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 22, "2010": 22},
                                        "best": {"2009": 22, "2010": 22},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 220, "2010": 220},
                                        "range": {"2009": 22, "2010": 22},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "GSHP": {
                                    "performance": {
                                        "typical": {"2009": 23, "2010": 23},
                                        "best": {"2009": 23, "2010": 23},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 23, "2010": 23},
                                        "best": {"2009": 23, "2010": 23},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 230, "2010": 230},
                                        "range": {"2009": 23, "2010": 23},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                    "performance": {
                                        "typical": {"2009": 24, "2010": 24},
                                        "best": {"2009": 24, "2010": 24},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 24, "2010": 24},
                                        "best": {"2009": 24, "2010": 24},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 240 * (3/24),
                                            "2010": 240 * (3/24)},
                                        "range": {"2009": 24, "2010": 24},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "general service (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 250 * (3/24),
                                            "2010": 250 * (3/24)},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "reflector (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 250 * (3/24),
                                            "2010": 250 * (3/24)},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "external (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 250 * (3/24),
                                            "2010": 250 * (3/24)},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}}}},
            "AIA_CZ2": {
                "single family home": {
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 1, "2010": 1},
                                        "best": {"2009": 1, "2010": 1},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 10, "2010": 10},
                                        "range": {"2009": 1, "2010": 1},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "resistance heat": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "ASHP": {
                                    "performance": {
                                        "typical": {"2009": 3, "2010": 3},
                                        "best": {"2009": 3, "2010": 3},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 3, "2010": 3},
                                        "best": {"2009": 3, "2010": 3},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 30, "2010": 30},
                                        "range": {"2009": 3, "2010": 3},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "GSHP": {
                                    "performance": {
                                        "typical": {"2009": 4, "2010": 4},
                                        "best": {"2009": 4, "2010": 4},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 4, "2010": 4},
                                        "best": {"2009": 4, "2010": 4},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 40, "2010": 40},
                                        "range": {"2009": 4, "2010": 4},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "secondary heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 5, "2010": 5},
                                        "best": {"2009": 5, "2010": 5},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 5, "2010": 5},
                                        "best": {"2009": 5, "2010": 5},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 50, "2010": 50},
                                        "range": {"2009": 5, "2010": 5},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 6, "2010": 6},
                                        "best": {"2009": 6, "2010": 6},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 6, "2010": 6},
                                        "best": {"2009": 6, "2010": 6},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 60, "2010": 60},
                                        "range": {"2009": 6, "2010": 6},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "non-specific": {
                                    "performance": {
                                        "typical": {"2009": 7, "2010": 7},
                                        "best": {"2009": 7, "2010": 7},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 7, "2010": 7},
                                        "best": {"2009": 7, "2010": 7},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 70, "2010": 70},
                                        "range": {"2009": 7, "2010": 7},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "cooling": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 8, "2010": 8},
                                        "best": {"2009": 8, "2010": 8},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 8, "2010": 8},
                                        "best": {"2009": 8, "2010": 8},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 80, "2010": 80},
                                        "range": {"2009": 8, "2010": 8},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 9, "2010": 9},
                                        "best": {"2009": 9, "2010": 9},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 9, "2010": 9},
                                        "best": {"2009": 9, "2010": 9},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 90, "2010": 90},
                                        "range": {"2009": 9, "2010": 9},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "infiltration": {
                                    "performance": {
                                        "typical": {"2009": 2, "2010": 3},
                                        "best": {"2009": 2, "2010": 3},
                                        "units": "ACH50",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 2, "2010": 2},
                                        "best": {"2009": 2, "2010": 2},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 20, "2010": 20},
                                        "range": {"2009": 2, "2010": 2},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "central AC": {
                                    "performance": {
                                        "typical": {"2009": 10, "2010": 10},
                                        "best": {"2009": 10, "2010": 10},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 10, "2010": 10},
                                        "best": {"2009": 10, "2010": 10},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 100, "2010": 100},
                                        "range": {"2009": 10, "2010": 10},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "room AC": {
                                    "performance": {
                                        "typical": {"2009": 11, "2010": 11},
                                        "best": {"2009": 11, "2010": 11},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 11, "2010": 11},
                                        "best": {"2009": 11, "2010": 11},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 110, "2010": 110},
                                        "range": {"2009": 11, "2010": 11},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "ASHP": {
                                    "performance": {
                                        "typical": {"2009": 12, "2010": 12},
                                        "best": {"2009": 12, "2010": 12},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 12, "2010": 12},
                                        "best": {"2009": 12, "2010": 12},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 120, "2010": 120},
                                        "range": {"2009": 12, "2010": 12},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "GSHP": {
                                    "performance": {
                                        "typical": {"2009": 13, "2010": 13},
                                        "best": {"2009": 13, "2010": 13},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 13, "2010": 13},
                                        "best": {"2009": 13, "2010": 13},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 130, "2010": 130},
                                        "range": {"2009": 13, "2010": 13},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                    "performance": {
                                        "typical": {"2009": 14, "2010": 14},
                                        "best": {"2009": 14, "2010": 14},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 14, "2010": 14},
                                        "best": {"2009": 14, "2010": 14},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 140 * (3/24),
                                            "2010": 140 * (3/24)},
                                        "range": {"2009": 14, "2010": 14},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "general service (LED)": {
                                    "performance": {
                                        "typical": {"2009": 15, "2010": 15},
                                        "best": {"2009": 15, "2010": 15},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 15, "2010": 15},
                                        "best": {"2009": 15, "2010": 15},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 150 * (3/24),
                                            "2010": 150 * (3/24)},
                                        "range": {"2009": 15, "2010": 15},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "reflector (LED)": {
                                    "performance": {
                                        "typical": {"2009": 16, "2010": 16},
                                        "best": {"2009": 16, "2010": 16},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 16, "2010": 16},
                                        "best": {"2009": 16, "2010": 16},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 160 * (3/24),
                                            "2010": 160 * (3/24)},
                                        "range": {"2009": 16, "2010": 16},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "external (LED)": {
                                    "performance": {
                                        "typical": {"2009": 17, "2010": 17},
                                        "best": {"2009": 17, "2010": 17},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 17, "2010": 17},
                                        "best": {"2009": 17, "2010": 17},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 170 * (3/24),
                                            "2010": 170 * (3/24)},
                                        "range": {"2009": 17, "2010": 17},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                        "TVs": {
                            "TVs": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}},
                            "set top box": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}}
                            },
                        "computers": {
                            "desktop PC": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}},
                            "laptop PC": {
                                "performance": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "installed cost": {
                                    "typical": {"2009": "NA", "2010": "NA"},
                                    "best": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "lifetime": {
                                    "average": {"2009": "NA", "2010": "NA"},
                                    "range": {"2009": "NA", "2010": "NA"},
                                    "units": "NA",
                                    "source": "NA"},
                                "consumer choice": {
                                    "competed market share": {
                                        "source": "EIA AEO",
                                        "model type":
                                            "logistic regression",
                                        "parameters": {
                                            "b1": {"2009": "NA",
                                                   "2010": "NA"},
                                            "b2": {"2009": "NA",
                                                   "2010": "NA"}}},
                                    "competed market": {
                                        "source": "COBAM",
                                        "model type": "bass diffusion",
                                        "parameters": {
                                            "p": "NA",
                                            "q": "NA"}}}}
                            }},
                    "natural gas": {
                        "water heating": {
                                "performance": {
                                    "typical": {"2009": 18, "2010": 18},
                                    "best": {"2009": 18, "2010": 18},
                                    "units": "EF",
                                    "source":
                                    "EIA AEO"},
                                "installed cost": {
                                    "typical": {"2009": 18, "2010": 18},
                                    "best": {"2009": 18, "2010": 18},
                                    "units": "2014$/unit",
                                    "source": "EIA AEO"},
                                "lifetime": {
                                    "average": {"2009": 180, "2010": 180},
                                    "range": {"2009": 18, "2010": 18},
                                    "units": "years",
                                    "source": "EIA AEO"},
                                "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                "multi family home": {
                    "electricity": {
                        "heating": {
                            "demand": {
                                "windows conduction": {
                                    "performance": {
                                        "typical": {"2009": 19, "2010": 19},
                                        "best": {"2009": 19, "2010": 19},
                                        "units": "R Value",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 19, "2010": 19},
                                        "best": {"2009": 19, "2010": 19},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 190, "2010": 190},
                                        "range": {"2009": 19, "2010": 19},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "windows solar": {
                                    "performance": {
                                        "typical": {"2009": 20, "2010": 20},
                                        "best": {"2009": 20, "2010": 20},
                                        "units": "SHGC",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 20, "2010": 20},
                                        "best": {"2009": 20, "2010": 20},
                                        "units": "2014$/ft^2 floor",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 200, "2010": 200},
                                        "range": {"2009": 20, "2010": 20},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}},
                            "supply": {
                                "resistance heat": {
                                    "performance": {
                                        "typical": {"2009": 21, "2010": 21},
                                        "best": {"2009": 21, "2010": 21},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 21, "2010": 21},
                                        "best": {"2009": 21, "2010": 21},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 210, "2010": 210},
                                        "range": {"2009": 21, "2010": 21},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "ASHP": {
                                    "performance": {
                                        "typical": {"2009": 22, "2010": 22},
                                        "best": {"2009": 22, "2010": 22},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 22, "2010": 22},
                                        "best": {"2009": 22, "2010": 22},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 220, "2010": 220},
                                        "range": {"2009": 22, "2010": 22},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                                "GSHP": {
                                    "performance": {
                                        "typical": {"2009": 23, "2010": 23},
                                        "best": {"2009": 23, "2010": 23},
                                        "units": "COP",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 23, "2010": 23},
                                        "best": {"2009": 23, "2010": 23},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 230, "2010": 230},
                                        "range": {"2009": 23, "2010": 23},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}},
                        "lighting": {
                            "linear fluorescent (LED)": {
                                    "performance": {
                                        "typical": {"2009": 24, "2010": 24},
                                        "best": {"2009": 24, "2010": 24},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 24, "2010": 24},
                                        "best": {"2009": 24, "2010": 24},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 240 * (3/24),
                                            "2010": 240 * (3/24)},
                                        "range": {"2009": 24, "2010": 24},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "general service (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 250 * (3/24),
                                            "2010": 250 * (3/24)},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "reflector (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 250 * (3/24),
                                            "2010": 250 * (3/24)},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "external (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {
                                            "2009": 250 * (3/24),
                                            "2010": 250 * (3/24)},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}}}},
            "AIA_CZ4": {
                "multi family home": {
                    "electricity": {
                        "lighting": {
                            "linear fluorescent (LED)": {
                                    "performance": {
                                        "typical": {"2009": 24, "2010": 24},
                                        "best": {"2009": 24, "2010": 24},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 24, "2010": 24},
                                        "best": {"2009": 24, "2010": 24},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 240, "2010": 240},
                                        "range": {"2009": 24, "2010": 24},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "general service (LED)": {
                                    "performance": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 25, "2010": 25},
                                        "best": {"2009": 25, "2010": 25},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 250, "2010": 250},
                                        "range": {"2009": 25, "2010": 25},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "reflector (LED)": {
                                    "performance": {
                                        "typical": {"2009": 26, "2010": 26},
                                        "best": {"2009": 26, "2010": 26},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 26, "2010": 26},
                                        "best": {"2009": 26, "2010": 26},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 260, "2010": 260},
                                        "range": {"2009": 26, "2010": 26},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}},
                            "external (LED)": {
                                    "performance": {
                                        "typical": {"2009": 27, "2010": 27},
                                        "best": {"2009": 27, "2010": 27},
                                        "units": "lm/W",
                                        "source":
                                        "EIA AEO"},
                                    "installed cost": {
                                        "typical": {"2009": 27, "2010": 27},
                                        "best": {"2009": 27, "2010": 27},
                                        "units": "2014$/unit",
                                        "source": "EIA AEO"},
                                    "lifetime": {
                                        "average": {"2009": 270, "2010": 270},
                                        "range": {"2009": 27, "2010": 27},
                                        "units": "years",
                                        "source": "EIA AEO"},
                                    "consumer choice": {
                                        "competed market share": {
                                            "source": "EIA AEO",
                                            "model type":
                                                "logistic regression",
                                            "parameters": {
                                                "b1": {"2009": "NA",
                                                       "2010": "NA"},
                                                "b2": {"2009": "NA",
                                                       "2010": "NA"}}},
                                        "competed market": {
                                            "source": "COBAM",
                                            "model type": "bass diffusion",
                                            "parameters": {
                                                "p": "NA",
                                                "q": "NA"}}}}}}}}}
        ok_measures_in = [{
            "name": "sample measure 1",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "AIA_CZ1": {"heating": 30,
                            "cooling": 25},
                "AIA_CZ2": {"heating": 30,
                            "cooling": 15}},
            "energy_efficiency_units": "COP",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["heating", "cooling"],
            "technology": ["resistance heat", "ASHP", "GSHP", "room AC"]},
            {
            "name": "sample measure 2",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {"new": 25, "existing": 25},
            "energy_efficiency_units": "EF",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1"],
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "water heating",
            "technology": None},
            {
            "name": "sample measure 3",
            "markets": None,
            "installed_cost": 500,
            "cost_units": {
                "refrigeration": "2010$/unit",
                "other (grid electric)": "2014$/unit"},
            "energy_efficiency": 0.1,
            "energy_efficiency_units": "relative savings (constant)",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["refrigeration", "other (grid electric)"],
            "technology": [None, "freezers"]},
            {
            "name": "sample measure 4",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": {
                "windows conduction": 20,
                "windows solar": 1},
            "energy_efficiency_units": {
                "windows conduction": "R Value",
                "windows solar": "SHGC"},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": "existing",
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "heating",
            "technology": [
                "windows conduction",
                "windows solar"]},
            {
            "name": "sample measure 5",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": 0.1,
            "energy_efficiency_units": "relative savings (constant)",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "add-on",
            "structure_type": "existing",
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "lighting",
            "technology": "linear fluorescent (LED)"},
            {
            "name": "sample measure 6",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": [
                    "heating", "secondary heating",
                    "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "sample measure 7",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": {
                "windows conduction": 20,
                "windows solar": 1},
            "energy_efficiency_units": {
                "windows conduction": "R Value",
                "windows solar": "SHGC"},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "heating",
            "technology": [
                "windows conduction",
                "windows solar"]},
            {
            "name": "sample measure 8",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": 1,
            "energy_efficiency_units": "SHGC",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "heating",
            "technology": "windows solar"},
            {
            "name": "sample measure 9",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": {
                "windows conduction": 10, "windows solar": 1},
            "energy_efficiency_units": {
                "windows conduction": "R Value",
                "windows solar": "SHGC"},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": [
                "heating", "secondary heating",
                "cooling"],
            "technology": [
                "windows conduction", "windows solar"]},
            {
            "name": "sample measure 10",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": {
                "windows conduction": 0.4,
                "windows solar": 1},
            "energy_efficiency_units": {
                "windows conduction": "relative savings (constant)",
                "windows solar": "SHGC"},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["heating", "secondary heating",
                        "cooling"],
            "technology": ["windows conduction",
                           "windows solar"]},
            {
            "name": "sample measure 11",  # Add heat/cool end uses later
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": 25,
            "energy_efficiency_units": "lm/W",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "assembly",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "lighting",
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": [
                "T5 F28"]},
            {
            "name": "sample measure 12",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": 25,
            "energy_efficiency_units": "EF",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": "new",
            "bldg_type": "single family home",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "water heating",
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": None},
            {
            "name": "sample measure 13",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": 25,
            "energy_efficiency_units": "EF",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": "existing",
            "bldg_type": "single family home",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "water heating",
            "technology": None},
            {
            "name": "sample measure 14",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": 2010,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": ["heating", "secondary heating",
                              "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "sample measure 15",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": None,
            "market_exit_year": 2010,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": ["heating", "secondary heating",
                              "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "sample measure 16",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": [
                    "relative savings (dynamic)", 2009]},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": ["heating", "secondary heating",
                              "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "sample measure 17",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "new": 25, "existing": 25},
            "energy_efficiency_units": "EF",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1"],
            "fuel_type": "natural gas",
            "fuel_switch_to": "electricity",
            "end_use": "water heating",
            "technology": None},
            {
            "name": "sample measure 18",
            "markets": None,
            "installed_cost": 11,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": 0.44,
            "energy_efficiency_units":
                "relative savings (constant)",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "add-on",
            "structure_type": ["new", "existing"],
            "bldg_type": "assembly",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "lighting",
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": [
                "T5 F28"]},
            {
            "name": "sample measure 19",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "new": 25, "existing": 25},
            "energy_efficiency_units": "EF",
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": {
                "new": 0.25,
                "existing": 0.5},
            "market_scaling_fractions_source": {
                "new": {
                    "title": 'Sample title 1',
                    "author": 'Sample author 1',
                    "organization": 'Sample org 1',
                    "year": 'Sample year 1',
                    "URL": ('http://www.eia.gov/consumption/'
                            'commercial/data/2012/'),
                    "fraction_derivation": "Divide X by Y"},
                "existing": {
                    "title": 'Sample title 1',
                    "author": 'Sample author 1',
                    "organization": 'Sample org 1',
                    "year": 'Sample year 1',
                    "URL": ('http://www.eia.gov/consumption/'
                            'commercial/data/2012/'),
                    "fraction_derivation": "Divide X by Y"}},
            "product_lifetime": 1,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "water heating",
            "technology": None},
            {
            "name": "sample measure 20",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": {
                "new": 0.25,
                "existing": 0.5},
            "market_scaling_fractions_source": {
                "new": {
                    "title": 'Sample title 2',
                    "author": 'Sample author 2',
                    "organization": 'Sample org 2',
                    "year": 'Sample year 2',
                    "URL": ('http://www.eia.gov/consumption/'
                            'commercial/data/2012/'),
                    "fraction_derivation": "Divide X by Y"},
                "existing": {
                    "title": 'Sample title 2',
                    "author": 'Sample author 2',
                    "organization": 'Sample org 2',
                    "year": 'Sample year 2',
                    "URL": ('http://www.eia.gov/consumption/'
                            'residential/data/2009/'),
                    "fraction_derivation": "Divide X by Y"}},
            "product_lifetime": 1,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home",
                          "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": ["heating", "secondary heating",
                              "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "sample measure 21",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "$/ft^2 floor",
            "energy_efficiency": 0.25,
            "energy_efficiency_units": "relative savings (constant)",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "add-on",
            "structure_type": ["new", "existing"],
            "bldg_type": "assembly",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["PCs", "MELs"],
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": [None, "distribution transformers"]},
            {
            "name": "sample measure 22",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "$/unit",
            "energy_efficiency": 0.5,
            "energy_efficiency_units": "relative savings (constant)",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "add-on",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["TVs", "computers", "other (grid electric)"],
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": ["TVs", "desktop PC", "laptop PC", "other MELs"]},
            {
            "name": "sample measure 23",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": 25,
            "energy_efficiency_units": "lm/W",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "assembly",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "lighting",
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": "T5 F28"}]
        cls.ok_tpmeas_fullchk_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in ok_measures_in[0:5]]
        cls.ok_tpmeas_partchk_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in ok_measures_in[5:22]]
        cls.ok_mapmeas_partchk_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in ok_measures_in[22:]]
        ok_distmeas_in = [{
            "name": "distrib measure 1",
            "markets": None,
            "installed_cost": ["normal", 25, 5],
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "AIA_CZ1": {
                    "heating": ["normal", 30, 1],
                    "cooling": ["normal", 25, 2]},
                "AIA_CZ2": {
                    "heating": 30,
                    "cooling": ["normal", 15, 4]}},
            "energy_efficiency_units": "COP",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["heating", "cooling"],
            "technology": ["resistance heat", "ASHP", "GSHP", "room AC"]},
            {
            "name": "distrib measure 2",
            "markets": None,
            "installed_cost": ["lognormal", 3.22, 0.06],
            "cost_units": "2014$/unit",
            "energy_efficiency": ["normal", 25, 5],
            "energy_efficiency_units": "EF",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": ["normal", 1, 1],
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home"],
            "climate_zone": ["AIA_CZ1"],
            "fuel_type": ["natural gas"],
            "fuel_switch_to": None,
            "end_use": "water heating",
            "technology": None},
            {
            "name": "distrib measure 3",
            "markets": None,
            "installed_cost": ["normal", 10, 5],
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": {
                "windows conduction": [
                    "lognormal", 2.29, 0.14],
                "windows solar": [
                    "normal", 1, 0.1]},
            "energy_efficiency_units": {
                "windows conduction": "R Value",
                "windows solar": "SHGC"},
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": ["single family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": [
                "heating", "secondary heating", "cooling"],
            "technology": [
                "windows conduction", "windows solar"]}]
        cls.ok_distmeas_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in ok_distmeas_in]
        ok_partialmeas_in = [{
            "name": "partial measure 1",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": 25,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "energy_efficiency_units": "COP",
            "market_entry_year": None,
            "market_exit_year": None,
            "bldg_type": ["single family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "cooling",
            "technology": ["resistance heat", "ASHP"]},
            {
            "name": "partial measure 2",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": 25,
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "energy_efficiency_units": "COP",
            "bldg_type": ["single family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["heating", "cooling"],
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)", "GSHP", "ASHP"]}]
        cls.ok_partialmeas_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in ok_partialmeas_in]
        failmeas_in = [{
            "name": "fail measure 1",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/unit",
            "energy_efficiency": 10,
            "energy_efficiency_units": "COP",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ19", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": "cooling",
            "technology": "resistance heat"},
            {
            "name": "fail measure 2",
            "markets": None,
            "installed_cost": 10,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "AIA_CZ1": {
                    "heating": 30, "cooling": 25},
                "AIA_CZ2": {
                    "heating": 30, "cooling": 15}},
            "energy_efficiency_units": "COP",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family homer",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["heating", "cooling"],
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "fail measure 3",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25, "secondary": None},
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["newer", "existing"],
            "energy_efficiency_units": {
                "primary": "lm/W", "secondary": None},
            "market_entry_year": None,
            "market_exit_year": None,
            "bldg_type": "single family home",
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": [
                    "heating", "secondary heating",
                    "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "fail measure 4",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25, "secondary": None},
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "energy_efficiency_units": {
                "primary": "lm/W", "secondary": None},
            "market_entry_year": None,
            "market_exit_year": None,
            "bldg_type": "single family home",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "solar",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": [
                    "heating", "secondary heating",
                    "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "fail measure 5",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/ft^2 floor",
            "energy_efficiency": 0.25,
            "energy_efficiency_units": "relative savings (constant)",
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "assembly",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": ["PCs", "MELs"],
            "market_entry_year": None,
            "market_exit_year": None,
            "technology": [None, "distribution transformers"]}]
        cls.failmeas_inputs_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in failmeas_in[0:-1]]
        cls.failmeas_missing_in = ecm_prep.Measure(
            handyvars, **failmeas_in[-1])
        warnmeas_in = [{
            "name": "warn measure 1",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": {
                "new": 0.25,
                "existing": 0.5},
            "market_scaling_fractions_source": {
                "new": {
                    "title": None,
                    "author": None,
                    "organization": None,
                    "year": None,
                    "URL": None,
                    "fraction_derivation": None},
                "existing": {
                    "title": None,
                    "author": None,
                    "organization": None,
                    "year": None,
                    "URL": None,
                    "fraction_derivation": None}},
            "product_lifetime": 1,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": [
                "single family home",
                "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": [
                    "heating", "secondary heating",
                    "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "warn measure 2",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": {
                "new": 0.25,
                "existing": 0.5},
            "market_scaling_fractions_source": {
                "new": {
                    "title": "Sample title",
                    "author": "Sample author",
                    "organization": "Sample organization",
                    "year": "http://www.sciencedirectcom",
                    "URL": "some BS",
                    "fraction_derivation": None},
                "existing": {
                    "title": "Sample title",
                    "author": "Sample author",
                    "organization": "Sample organization",
                    "year": "Sample year",
                    "URL": "http://www.sciencedirect.com",
                    "fraction_derivation": None}},
            "product_lifetime": 1,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": [
                "single family home",
                "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": [
                    "heating", "secondary heating",
                    "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]},
            {
            "name": "warn measure 3",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "primary": 25,
                "secondary": {
                    "heating": 0.4,
                    "secondary heating": 0.4,
                    "cooling": -0.4}},
            "energy_efficiency_units": {
                "primary": "lm/W",
                "secondary": "relative savings (constant)"},
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": {
                "new": 0.25,
                "existing": 0.5},
            "market_scaling_fractions_source": {
                "new": {
                    "title": "Sample title",
                    "author": None,
                    "organization": "Sample organization",
                    "year": "Sample year",
                    "URL": "https://bpd.lbl.gov/",
                    "fraction_derivation": "Divide X by Y"},
                "existing": {
                    "title": "Sample title",
                    "author": None,
                    "organization": "Sample organization",
                    "year": "Sample year",
                    "URL": "https://cms.doe.gov/data/green-button",
                    "fraction_derivation": "Divide X by Y"}},
            "product_lifetime": 1,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": [
                "single family home",
                "multi family home"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": {
                "primary": "lighting",
                "secondary": [
                    "heating", "secondary heating",
                    "cooling"]},
            "technology": [
                "linear fluorescent (LED)",
                "general service (LED)",
                "external (LED)"]}]
        cls.warnmeas_in = [
            ecm_prep.Measure(
                handyvars, **x) for x in warnmeas_in]
        cls.ok_tpmeas_fullchk_msegout = [{
            "stock": {
                "total": {
                    "all": {"2009": 72, "2010": 72},
                    "measure": {"2009": 72, "2010": 72}},
                "competed": {
                    "all": {"2009": 72, "2010": 72},
                    "measure": {"2009": 72, "2010": 72}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 229.68, "2010": 230.4},
                    "efficient": {"2009": 117.0943, "2010": 117.4613}},
                "competed": {
                    "baseline": {"2009": 229.68, "2010": 230.4},
                    "efficient": {"2009": 117.0943, "2010": 117.4613}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 13056.63, "2010": 12941.16},
                    "efficient": {"2009": 6656.461, "2010": 6597.595}},
                "competed": {
                    "baseline": {"2009": 13056.63, "2010": 12941.16},
                    "efficient": {"2009": 6656.461, "2010": 6597.595}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 710, "2010": 710},
                        "efficient": {"2009": 1800, "2010": 1800}},
                    "competed": {
                        "baseline": {"2009": 710, "2010": 710},
                        "efficient": {"2009": 1800, "2010": 1800}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 2328.955, "2010": 2227.968},
                        "efficient": {"2009": 1187.336, "2010": 1135.851}},
                    "competed": {
                        "baseline": {"2009": 2328.955, "2010": 2227.968},
                        "efficient": {"2009": 1187.336, "2010": 1135.851}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 430868.63, "2010": 427058.3},
                        "efficient": {"2009": 219663.21, "2010": 217720.65}},
                    "competed": {
                        "baseline": {"2009": 430868.63, "2010": 427058.3},
                        "efficient": {"2009": 219663.21, "2010": 217720.65}}}},
            "lifetime": {"baseline": {"2009": 98.61, "2010": 98.61},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 15, "2010": 15},
                    "measure": {"2009": 15, "2010": 15}},
                "competed": {
                    "all": {"2009": 15, "2010": 15},
                    "measure": {"2009": 15, "2010": 15}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 15.15, "2010": 15.15},
                    "efficient": {"2009": 10.908, "2010": 10.908}},
                "competed": {
                    "baseline": {"2009": 15.15, "2010": 15.15},
                    "efficient": {"2009": 10.908, "2010": 10.908}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 856.2139, "2010": 832.0021},
                    "efficient": {"2009": 616.474, "2010": 599.0415}},
                "competed": {
                    "baseline": {"2009": 856.2139, "2010": 832.0021},
                    "efficient": {"2009": 616.474, "2010": 599.0415}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 270, "2010": 270},
                        "efficient": {"2009": 375, "2010": 375}},
                    "competed": {
                        "baseline": {"2009": 270, "2010": 270},
                        "efficient": {"2009": 375, "2010": 375}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 170.892, "2010": 163.317},
                        "efficient": {"2009": 123.0422, "2010": 117.5882}},
                    "competed": {
                        "baseline": {"2009": 170.892, "2010": 163.317},
                        "efficient": {"2009": 123.0422, "2010": 117.5882}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 28255.06, "2010": 27456.07},
                        "efficient": {"2009": 20343.64, "2010": 19768.37}},
                    "competed": {
                        "baseline": {"2009": 28255.06, "2010": 27456.07},
                        "efficient": {"2009": 20343.64, "2010": 19768.37}}}},
            "lifetime": {"baseline": {"2009": 180, "2010": 180},
                         "measure": 1}},
                        {
            "stock": {
                "total": {
                    "all": {"2009": 333, "2010": 333},
                    "measure": {"2009": 333, "2010": 333}},
                "competed": {
                    "all": {"2009": 333, "2010": 333},
                    "measure": {"2009": 333, "2010": 333}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 1062.27, "2010": 1065.6},
                    "efficient": {"2009": 956.043, "2010": 959.04}},
                "competed": {
                    "baseline": {"2009": 1062.27, "2010": 1065.6},
                    "efficient": {"2009": 956.043, "2010": 959.04}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 60386.89, "2010": 59852.87},
                    "efficient": {"2009": 54348.2, "2010": 53867.58}},
                "competed": {
                    "baseline": {"2009": 60386.89, "2010": 59852.87},
                    "efficient": {"2009": 54348.2, "2010": 53867.58}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 55500, "2010": 55500},
                        "efficient": {"2009": 166500, "2010": 166500}},
                    "competed": {
                        "baseline": {"2009": 55500, "2010": 55500},
                        "efficient": {"2009": 166500, "2010": 166500}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 10771.42, "2010": 10304.35},
                        "efficient": {"2009": 9694.276, "2010": 9273.917}},
                    "competed": {
                        "baseline": {"2009": 10771.42, "2010": 10304.35},
                        "efficient": {"2009": 9694.276, "2010": 9273.917}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 1992767.41, "2010": 1975144.64},
                        "efficient": {"2009": 1793490.67, "2010": 1777630.18}},
                    "competed": {
                        "baseline": {"2009": 1992767.41, "2010": 1975144.64},
                        "efficient": {
                            "2009": 1793490.67, "2010": 1777630.18}}}},
            "lifetime": {"baseline": {"2009": 15.67, "2010": 15.67},
                         "measure": 1}}]
        # Correct consumer choice dict outputs
        compete_choice_val = [{
            "b1": {"2009": -0.01, "2010": -0.01},
            "b2": {"2009": -0.12, "2010": -0.12}},
            {
            "b1": {"2009": -0.01 * handyvars.res_typ_sf_household[
                    "single family home"],
                   "2010": -0.01 * handyvars.res_typ_sf_household[
                   "single family home"]},
            "b2": {"2009": -0.12 * handyvars.res_typ_sf_household[
                    "single family home"],
                   "2010": -0.12 * handyvars.res_typ_sf_household[
                   "single family home"]}},
            {
            "b1": {"2009": -0.01 * handyvars.res_typ_sf_household[
                    "multi family home"],
                   "2010": -0.01 * handyvars.res_typ_sf_household[
                    "multi family home"]},
            "b2": {"2009": -0.12 * handyvars.res_typ_sf_household[
                    "multi family home"],
                   "2010": -0.12 * handyvars.res_typ_sf_household[
                   "multi family home"]}},
            {
            "b1": {
                "2009": -0.01 * handyvars.res_typ_sf_household[
                    "single family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["single family home"],
                "2010": -0.01 * handyvars.res_typ_sf_household[
                   "single family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["single family home"]},
            "b2": {
                "2009": -0.12 * handyvars.res_typ_sf_household[
                    "single family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["single family home"],
                "2010": -0.12 * handyvars.res_typ_sf_household[
                   "single family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["single family home"]}},
            {
            "b1": {
                "2009": -0.01 * handyvars.res_typ_sf_household[
                    "multi family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["multi family home"],
                "2010": -0.01 * handyvars.res_typ_sf_household[
                    "multi family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["multi family home"]},
            "b2": {
                "2009": -0.12 * handyvars.res_typ_sf_household[
                    "multi family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["multi family home"],
                "2010": -0.12 * handyvars.res_typ_sf_household[
                   "multi family home"] /
                handyvars.res_typ_units_household[
                    "lighting"]["multi family home"]}}]
        cls.ok_tpmeas_fullchk_competechoiceout = [{
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'resistance heat', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'ASHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'GSHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'ASHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'GSHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'room AC', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'resistance heat', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'ASHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'GSHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'ASHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'GSHP', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'room AC', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'resistance heat', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'ASHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'GSHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'ASHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'GSHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'room AC', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'resistance heat', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'ASHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'supply', "
             "'GSHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'ASHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'GSHP', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'cooling', 'supply', "
             "'room AC', 'existing')"): compete_choice_val[0]},
            {
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'natural gas', 'water heating', "
             "None, 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'natural gas', 'water heating', "
             "None, 'existing')"): compete_choice_val[0]},
            {
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'other (grid electric)', "
             "'freezers', 'new')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'other (grid electric)', "
             "'freezers', 'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'refrigeration', None, "
             "'existing')"): compete_choice_val[0],
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'refrigeration', None, "
             "'new')"): compete_choice_val[0]},
            {
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'heating', 'demand', 'windows', "
             "'existing')"): compete_choice_val[1],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'heating', 'demand', 'windows', "
             "'existing')"): compete_choice_val[1],
            ("('primary', 'AIA_CZ1', 'multi family home', "
             "'electricity', 'heating', 'demand', 'windows', "
             "'existing')"): compete_choice_val[2],
            ("('primary', 'AIA_CZ2', 'multi family home', "
             "'electricity', 'heating', 'demand', 'windows', "
             "'existing')"): compete_choice_val[2]},
            {
            ("('primary', 'AIA_CZ1', 'single family home', "
             "'electricity', 'lighting', 'linear fluorescent (LED)', "
             "'existing')"): compete_choice_val[3],
            ("('primary', 'AIA_CZ2', 'single family home', "
             "'electricity', 'lighting', 'linear fluorescent (LED)', "
             "'existing')"): compete_choice_val[3],
            ("('primary', 'AIA_CZ1', 'multi family home', "
             "'electricity', 'lighting', 'linear fluorescent (LED)', "
             "'existing')"): compete_choice_val[4],
            ("('primary', 'AIA_CZ2', 'multi family home', "
             "'electricity', 'lighting', 'linear fluorescent (LED)', "
             "'existing')"): compete_choice_val[4]}]
        cls.ok_tpmeas_fullchk_msegadjout = [{
            "sub-market": {
                "original energy (total)": {},
                "adjusted energy (sub-market)": {}},
            "stock-and-flow": {
                "original energy (total)": {},
                "adjusted energy (previously captured)": {},
                "adjusted energy (competed)": {},
                "adjusted energy (competed and captured)": {}},
            "market share": {
                "original energy (total captured)": {},
                "original energy (competed and captured)": {},
                "adjusted energy (total captured)": {},
                "adjusted energy (competed and captured)": {}}},
            {
            "sub-market": {
                "original energy (total)": {},
                "adjusted energy (sub-market)": {}},
            "stock-and-flow": {
                "original energy (total)": {},
                "adjusted energy (previously captured)": {},
                "adjusted energy (competed)": {},
                "adjusted energy (competed and captured)": {}},
            "market share": {
                "original energy (total captured)": {},
                "original energy (competed and captured)": {},
                "adjusted energy (total captured)": {},
                "adjusted energy (competed and captured)": {}}},
            {
            "sub-market": {
                "original energy (total)": {},
                "adjusted energy (sub-market)": {}},
            "stock-and-flow": {
                "original energy (total)": {},
                "adjusted energy (previously captured)": {},
                "adjusted energy (competed)": {},
                "adjusted energy (competed and captured)": {}},
            "market share": {
                "original energy (total captured)": {},
                "original energy (competed and captured)": {},
                "adjusted energy (total captured)": {},
                "adjusted energy (competed and captured)": {}}}]
        cls.ok_tpmeas_fullchk_supplydemandout = [{
            "savings": {
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'new')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 0, "2010": 0},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'existing')"): {"2009": 0, "2010": 0}},
            "total": {
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'new')"): {
                    "2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'new')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'new')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'new')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'new')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'new')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'new')"): {
                    "2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'new')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'new')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'new')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'new')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'new')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'existing')"): {
                    "2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ1', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'existing')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'resistance heat', 'existing')"): {
                    "2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'heating', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 28.71, "2010": 28.80},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'ASHP', 'existing')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'GSHP', 'existing')"): {"2009": 108.46, "2010": 108.8},
                ("('primary', 'AIA_CZ2', 'single family home', "
                 "'electricity', 'cooling', 'supply', "
                 "'room AC', 'existing')"): {"2009": 108.46, "2010": 108.8}}},
            {"savings": {}, "total": {}},
            {"savings": {}, "total": {}}]
        cls.ok_tpmeas_fullchk_break_out = [{
            'AIA CZ1': {
                'Residential (New)': {
                    'Cooling (Equip.)': {"2009": 0.0375, "2010": 0.05625},
                    'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {},
                    'Heating (Equip.)': {"2009": 0.0125, "2010": 0.01875},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {"2009": 0.3375, "2010": 0.31875},
                    'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {},
                    'Heating (Equip.)': {"2009": 0.1125, "2010": 0.10625},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ2': {
                'Residential (New)': {
                    'Cooling (Equip.)': {"2009": 0.0375, "2010": 0.05625},
                    'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {},
                    'Heating (Equip.)': {"2009": 0.0125, "2010": 0.01875},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {"2009": 0.3375, "2010": 0.31875},
                    'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {},
                    'Heating (Equip.)': {"2009": 0.1125, "2010": 0.10625},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ3': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ4': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ5': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}}},
            {
            'AIA CZ1': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {},
                    'Water Heating': {"2009": 0.10, "2010": 0.15},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {},
                    'Water Heating': {"2009": 0.90, "2010": 0.85},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ2': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ3': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ4': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ5': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}}},
            {
            'AIA CZ1': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {"2009": 0.10, "2010": 0.15},
                    'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {"2009": 0.90, "2010": 0.85},
                    'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ2': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ3': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ4': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}},
            'AIA CZ5': {
                'Residential (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Residential (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (New)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}},
                'Commercial (Existing)': {
                    'Cooling (Equip.)': {}, 'Ventilation': {}, 'Lighting': {},
                    'Refrigeration': {}, 'Other': {}, 'Water Heating': {},
                    'Computers and Electronics': {}, 'Heating (Equip.)': {},
                    'Envelope': {}}}}]
        cls.ok_tpmeas_partchk_msegout = [{
            "stock": {
                "total": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 148, "2010": 148}},
                "competed": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 148, "2010": 148}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 647.8339, "2010": 649.7508}},
                "competed": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 647.8339, "2010": 649.7508}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 36815.4, "2010": 36449.93}},
                "competed": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 36815.4, "2010": 36449.93}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 3700, "2010": 3700}},
                    "competed": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 3700, "2010": 3700}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 6610.44, "2010": 6323.41}},
                    "competed": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 6610.44, "2010": 6323.41}}},
                "carbon": {
                    "total": {
                        "baseline": {
                            "2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {
                            "2009": 1214908.11, "2010": 1202847.67}},
                    "competed": {
                        "baseline": {
                            "2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {
                            "2009": 1214908.11, "2010": 1202847.67}}}},
            "lifetime": {"baseline": {"2009": 200.8108, "2010": 200.8108},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 1600000000, "2010": 2000000000},
                    "measure": {"2009": 1600000000, "2010": 2000000000}},
                "competed": {
                    "all": {"2009": 1600000000, "2010": 2000000000},
                    "measure": {"2009": 1600000000, "2010": 2000000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 12.76, "2010": 12.8},
                    "efficient": {"2009": 3.509, "2010": 3.52}},
                "competed": {
                    "baseline": {"2009": 12.76, "2010": 12.8},
                    "efficient": {"2009": 3.509, "2010": 3.52}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 725.3681, "2010": 718.9534},
                    "efficient": {"2009": 199.4762, "2010": 197.7122}},
                "competed": {
                    "baseline": {"2009": 725.3681, "2010": 718.9534},
                    "efficient": {"2009": 199.4762, "2010": 197.7122}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {
                            "2009": 20400000000, "2010": 24600000000},
                        "efficient": {
                            "2009": 16000000000, "2010": 20000000000}},
                    "competed": {
                        "baseline": {
                            "2009": 20400000000, "2010": 24600000000},
                        "efficient": {
                            "2009": 16000000000, "2010": 20000000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 129.3864, "2010": 123.776},
                        "efficient": {"2009": 35.58126, "2010": 34.0384}},
                    "competed": {
                        "baseline": {"2009": 129.3864, "2010": 123.776},
                        "efficient": {"2009": 35.58126, "2010": 34.0384}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 23937.15, "2010": 23725.46},
                        "efficient": {"2009": 6582.715, "2010": 6524.502}},
                    "competed": {
                        "baseline": {"2009": 23937.15, "2010": 23725.46},
                        "efficient": {"2009": 6582.715, "2010": 6524.502}}}},
            "lifetime": {"baseline": {"2009": 127.5, "2010": 123},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 600000000, "2010": 800000000},
                    "measure": {"2009": 600000000, "2010": 800000000}},
                "competed": {
                    "all": {"2009": 600000000, "2010": 800000000},
                    "measure": {"2009": 600000000, "2010": 800000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 6.38, "2010": 6.4},
                    "efficient": {"2009": 3.19, "2010": 3.2}},
                "competed": {
                    "baseline": {"2009": 6.38, "2010": 6.4},
                    "efficient": {"2009": 3.19, "2010": 3.2}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 362.684, "2010": 359.4767},
                    "efficient": {"2009": 181.342, "2010": 179.7383}},
                "competed": {
                    "baseline": {"2009": 362.684, "2010": 359.4767},
                    "efficient": {"2009": 181.342, "2010": 179.7383}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {
                            "2009": 900000000, "2010": 1200000000},
                        "efficient": {
                            "2009": 6000000000, "2010": 8000000000}},
                    "competed": {
                        "baseline": {
                            "2009": 900000000, "2010": 1200000000},
                        "efficient": {
                            "2009": 6000000000, "2010": 8000000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 64.6932, "2010": 61.888},
                        "efficient": {"2009": 32.3466, "2010": 30.944}},
                    "competed": {
                        "baseline": {"2009": 64.6932, "2010": 61.888},
                        "efficient": {"2009": 32.3466, "2010": 30.944}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 11968.57, "2010": 11862.73},
                        "efficient": {"2009": 5984.287, "2010": 5931.365}},
                    "competed": {
                        "baseline": {"2009": 11968.57, "2010": 11862.73},
                        "efficient": {"2009": 5984.287, "2010": 5931.365}}}},
            "lifetime": {"baseline": {"2009": 15, "2010": 15},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 600000000, "2010": 800000000},
                    "measure": {"2009": 600000000, "2010": 800000000}},
                "competed": {
                    "all": {"2009": 600000000, "2010": 800000000},
                    "measure": {"2009": 600000000, "2010": 800000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 146.74, "2010": 147.2},
                    "efficient": {"2009": 55.29333, "2010": 55.46667}},
                "competed": {
                    "baseline": {"2009": 146.74, "2010": 147.2},
                    "efficient": {"2009": 55.29333, "2010": 55.46667}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 8341.733, "2010": 8267.964},
                    "efficient": {"2009": 3143.262, "2010": 3115.465}},
                "competed": {
                    "baseline": {"2009": 8341.733, "2010": 8267.964},
                    "efficient": {"2009": 3143.262, "2010": 3115.465}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {
                            "2009": 3100000000, "2010": 4133333333.33},
                        "efficient": {
                            "2009": 6000000000, "2010": 8000000000}},
                    "competed": {
                        "baseline": {
                            "2009": 3100000000, "2010": 4133333333.33},
                        "efficient": {
                            "2009": 6000000000, "2010": 8000000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 1487.944, "2010": 1423.424},
                        "efficient": {"2009": 560.6744, "2010": 536.3627}},
                    "competed": {
                        "baseline": {"2009": 1487.944, "2010": 1423.424},
                        "efficient": {"2009": 560.6744, "2010": 536.3627}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 275277.18, "2010": 272842.8},
                        "efficient": {"2009": 103727.63, "2010": 102810.33}},
                    "competed": {
                        "baseline": {"2009": 275277.18, "2010": 272842.8},
                        "efficient": {"2009": 103727.63, "2010": 102810.33}}}},
            "lifetime": {"baseline": {"2009": 51.67, "2010": 51.67},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 600000000, "2010": 800000000},
                    "measure": {"2009": 600000000, "2010": 800000000}},
                "competed": {
                    "all": {"2009": 600000000, "2010": 800000000},
                    "measure": {"2009": 600000000, "2010": 800000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 146.74, "2010": 147.2},
                    "efficient": {"2009": 52.10333, "2010": 52.26667}},
                "competed": {
                    "baseline": {"2009": 146.74, "2010": 147.2},
                    "efficient": {"2009": 52.10333, "2010": 52.26667}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 8341.733, "2010": 8267.964},
                    "efficient": {"2009": 2961.92, "2010": 2935.726}},
                "competed": {
                    "baseline": {"2009": 8341.733, "2010": 8267.964},
                    "efficient": {"2009": 2961.92, "2010": 2935.726}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {
                            "2009": 3100000000, "2010": 4133333333.33},
                        "efficient": {
                            "2009": 6000000000, "2010": 8000000000}},
                    "competed": {
                        "baseline": {
                            "2009": 3100000000, "2010": 4133333333.33},
                        "efficient": {
                            "2009": 6000000000, "2010": 8000000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 1487.944, "2010": 1423.424},
                        "efficient": {"2009": 528.3278, "2010": 505.4187}},
                    "competed": {
                        "baseline": {"2009": 1487.944, "2010": 1423.424},
                        "efficient": {"2009": 528.3278, "2010": 505.4187}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 275277.18, "2010": 272842.8},
                        "efficient": {"2009": 97743.35, "2010": 96878.97}},
                    "competed": {
                        "baseline": {"2009": 275277.18, "2010": 272842.8},
                        "efficient": {"2009": 97743.35, "2010": 96878.97}}}},
            "lifetime": {"baseline": {"2009": 51.67, "2010": 51.67},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 11000000, "2010": 11000000}},
                "competed": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 11000000, "2010": 11000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 31.9, "2010": 32.0},
                    "efficient": {"2009": 17.86, "2010": 17.92}},
                "competed": {
                    "baseline": {"2009": 31.9, "2010": 32.0},
                    "efficient": {"2009": 17.86, "2010": 17.92}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 1813.42, "2010": 1797.38},
                    "efficient": {"2009": 1015.52, "2010": 1006.53}},
                "competed": {
                    "baseline": {"2009": 1813.42, "2010": 1797.38},
                    "efficient": {"2009": 1015.52, "2010": 1006.53}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 154000000, "2010": 154000000},
                        "efficient": {"2009": 275000000, "2010": 275000000}},
                    "competed": {
                        "baseline": {"2009": 154000000, "2010": 154000000},
                        "efficient": {"2009": 275000000, "2010": 275000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 289.65, "2010": 273.6},
                        "efficient": {"2009": 162.21, "2010": 153.22}},
                    "competed": {
                        "baseline": {"2009": 289.65, "2010": 273.6},
                        "efficient": {"2009": 162.21, "2010": 153.22}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 59842.87, "2010": 59313.65},
                        "efficient": {"2009": 33512, "2010": 33215.65}},
                    "competed": {
                        "baseline": {"2009": 59842.87, "2010": 59313.65},
                        "efficient": {"2009": 33512, "2010": 33215.65}}}},
            "lifetime": {"baseline": {"2009": 140, "2010": 140},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 1.5, "2010": 2.25},
                    "measure": {"2009": 1.5, "2010": 2.25}},
                "competed": {
                    "all": {"2009": 1.5, "2010": 2.25},
                    "measure": {"2009": 1.5, "2010": 2.25}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 1.515, "2010": 2.2725},
                    "efficient": {"2009": 1.0908, "2010": 1.6362}},
                "competed": {
                    "baseline": {"2009": 1.515, "2010": 2.2725},
                    "efficient": {"2009": 1.0908, "2010": 1.6362}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 85.62139, "2010": 124.8003},
                    "efficient": {"2009": 61.6474, "2010": 89.85622}},
                "competed": {
                    "baseline": {"2009": 85.62139, "2010": 124.8003},
                    "efficient": {"2009": 61.6474, "2010": 89.85622}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 27, "2010": 40.5},
                        "efficient": {"2009": 37.5, "2010": 56.25}},
                    "competed": {
                        "baseline": {"2009": 27, "2010": 40.5},
                        "efficient": {"2009": 37.5, "2010": 56.25}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 17.0892, "2010": 24.49755},
                        "efficient": {"2009": 12.30422, "2010": 17.63823}},
                    "competed": {
                        "baseline": {"2009": 17.0892, "2010": 24.49755},
                        "efficient": {"2009": 12.30422, "2010": 17.63823}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 2825.506, "2010": 4118.409},
                        "efficient": {"2009": 2034.364, "2010": 2965.256}},
                    "competed": {
                        "baseline": {"2009": 2825.506, "2010": 4118.409},
                        "efficient": {"2009": 2034.364, "2010": 2965.256}}}},
            "lifetime": {"baseline": {"2009": 180, "2010": 180},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 13.5, "2010": 12.75},
                    "measure": {"2009": 13.5, "2010": 12.75}},
                "competed": {
                    "all": {"2009": 13.5, "2010": 12.75},
                    "measure": {"2009": 13.5, "2010": 12.75}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 13.635, "2010": 12.8775},
                    "efficient": {"2009": 9.8172, "2010": 9.2718}},
                "competed": {
                    "baseline": {"2009": 13.635, "2010": 12.8775},
                    "efficient": {"2009": 9.8172, "2010": 9.2718}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 770.5925, "2010": 707.2018},
                    "efficient": {"2009": 554.8266, "2010": 509.1853}},
                "competed": {
                    "baseline": {"2009": 770.5925, "2010": 707.2018},
                    "efficient": {"2009": 554.8266, "2010": 509.1853}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 243, "2010": 229.5},
                        "efficient": {"2009": 337.5, "2010": 318.75}},
                    "competed": {
                        "baseline": {"2009": 243, "2010": 229.5},
                        "efficient": {"2009": 337.5, "2010": 318.75}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 153.8028, "2010": 138.8195},
                        "efficient": {"2009": 110.738, "2010": 99.94998}},
                    "competed": {
                        "baseline": {"2009": 153.8028, "2010": 138.8195},
                        "efficient": {"2009": 110.738, "2010": 99.94998}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 25429.55, "2010": 23337.66},
                        "efficient": {"2009": 18309.28, "2010": 16803.11}},
                    "competed": {
                        "baseline": {"2009": 25429.55, "2010": 23337.66},
                        "efficient": {"2009": 18309.28, "2010": 16803.11}}}},
            "lifetime": {"baseline": {"2009": 180, "2010": 180},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 0, "2010": 148}},
                "competed": {
                    "all": {"2009": 18.17, "2010": 148},
                    "measure": {"2009": 0, "2010": 148}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 766.677, "2010": 649.7508}},
                "competed": {
                    "baseline": {"2009": 94.42735, "2010": 768.9562},
                    "efficient": {"2009": 94.42735, "2010": 649.7508}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 43570.19, "2010": 36449.93}},
                "competed": {
                    "baseline": {"2009": 5366.289, "2010": 43141.37},
                    "efficient": {"2009": 5366.289, "2010": 36449.93}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 2972, "2010": 3700}},
                    "competed": {
                        "baseline": {"2009": 364.016, "2010": 2972},
                        "efficient": {"2009": 364.016, "2010": 3700}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 7819.26, "2010": 6323.41}},
                    "competed": {
                        "baseline": {"2009": 963.0867, "2010": 7479.78},
                        "efficient": {"2009": 963.0867, "2010": 6323.41}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {"2009": 1437816.14, "2010": 1202847.67}},
                    "competed": {
                        "baseline": {"2009": 177087.54, "2010": 1423665.24},
                        "efficient": {
                            "2009": 177087.54, "2010": 1202847.67}}}},
            "lifetime": {"baseline": {"2009": 200.81, "2010": 200.81},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 148, "2010": 0}},
                "competed": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 148, "2010": 0}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 647.8339, "2010": 768.9562}},
                "competed": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 647.8339, "2010": 768.9562}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 36815.4, "2010": 43141.37}},
                "competed": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 36815.4, "2010": 43141.37}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 3700, "2010": 2972}},
                    "competed": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 3700, "2010": 2972}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 6610.44, "2010": 7479.78}},
                    "competed": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 6610.44, "2010": 7479.78}}},
                "carbon": {
                    "total": {
                        "baseline": {
                            "2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {
                            "2009": 1214908.11, "2010": 1423665.24}},
                    "competed": {
                        "baseline": {
                            "2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {
                            "2009": 1214908.11, "2010": 1423665.24}}}},
            "lifetime": {"baseline": {"2009": 200.8108, "2010": 200.8108},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 148, "2010": 148}},
                "competed": {
                    "all": {"2009": 148, "2010": 148},
                    "measure": {"2009": 148, "2010": 148}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 647.8339, "2010": 649.7508}},
                "competed": {
                    "baseline": {"2009": 766.677, "2010": 768.9562},
                    "efficient": {"2009": 647.8339, "2010": 649.7508}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 36815.4, "2010": 36449.93}},
                "competed": {
                    "baseline": {"2009": 43570.19, "2010": 43141.37},
                    "efficient": {"2009": 36815.4, "2010": 36449.93}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 3700, "2010": 3700}},
                    "competed": {
                        "baseline": {"2009": 2972, "2010": 2972},
                        "efficient": {"2009": 3700, "2010": 3700}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 6610.44, "2010": 6323.41}},
                    "competed": {
                        "baseline": {"2009": 7819.26, "2010": 7479.78},
                        "efficient": {"2009": 6610.44, "2010": 6323.41}}},
                "carbon": {
                    "total": {
                        "baseline": {
                            "2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {
                            "2009": 1214908.11, "2010": 1202847.67}},
                    "competed": {
                        "baseline": {
                            "2009": 1437816.14, "2010": 1423665.24},
                        "efficient": {
                            "2009": 1214908.11, "2010": 1202847.67}}}},
            "lifetime": {"baseline": {"2009": 200.8108, "2010": 200.8108},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 15, "2010": 15},
                    "measure": {"2009": 15, "2010": 15}},
                "competed": {
                    "all": {"2009": 15, "2010": 15},
                    "measure": {"2009": 15, "2010": 15}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 15.15, "2010": 15.15},
                    "efficient": {"2009": 34.452, "2010": 34.56}},
                "competed": {
                    "baseline": {"2009": 15.15, "2010": 15.15},
                    "efficient": {"2009": 34.452, "2010": 34.56}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 856.2139, "2010": 832.0021},
                    "efficient": {"2009": 1958.494, "2010": 1941.174}},
                "competed": {
                    "baseline": {"2009": 856.2139, "2010": 832.0021},
                    "efficient": {"2009": 1958.494, "2010": 1941.174}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 270, "2010": 270},
                        "efficient": {"2009": 375, "2010": 375}},
                    "competed": {
                        "baseline": {"2009": 270, "2010": 270},
                        "efficient": {"2009": 375, "2010": 375}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 170.892, "2010": 163.317},
                        "efficient": {"2009": 349.3433, "2010": 334.1952}},
                    "competed": {
                        "baseline": {"2009": 170.892, "2010": 163.317},
                        "efficient": {"2009": 349.3433, "2010": 334.1952}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 28255.06, "2010": 27456.07},
                        "efficient": {"2009": 64630.29, "2010": 64058.75}},
                    "competed": {
                        "baseline": {"2009": 28255.06, "2010": 27456.07},
                        "efficient": {"2009": 64630.29, "2010": 64058.75}}}},
            "lifetime": {"baseline": {"2009": 180, "2010": 180},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 11000000, "2010": 11000000}},
                "competed": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 11000000, "2010": 11000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 31.9, "2010": 32.0},
                    "efficient": {"2009": 17.86, "2010": 17.92}},
                "competed": {
                    "baseline": {"2009": 31.9, "2010": 32.0},
                    "efficient": {"2009": 17.86, "2010": 17.92}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 1813.42, "2010": 1797.38},
                    "efficient": {"2009": 1015.52, "2010": 1006.53}},
                "competed": {
                    "baseline": {"2009": 1813.42, "2010": 1797.38},
                    "efficient": {"2009": 1015.52, "2010": 1006.53}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 154000000, "2010": 154000000},
                        "efficient": {"2009": 275000000, "2010": 275000000}},
                    "competed": {
                        "baseline": {"2009": 154000000, "2010": 154000000},
                        "efficient": {"2009": 275000000, "2010": 275000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 289.65, "2010": 273.6},
                        "efficient": {"2009": 162.21, "2010": 153.22}},
                    "competed": {
                        "baseline": {"2009": 289.65, "2010": 273.6},
                        "efficient": {"2009": 162.21, "2010": 153.22}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 59842.87, "2010": 59313.65},
                        "efficient": {"2009": 33512, "2010": 33215.65}},
                    "competed": {
                        "baseline": {"2009": 59842.87, "2010": 59313.65},
                        "efficient": {"2009": 33512, "2010": 33215.65}}}},
            "lifetime": {"baseline": {"2009": 140, "2010": 140},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 7.125, "2010": 6.9375},
                    "measure": {"2009": 7.125, "2010": 6.9375}},
                "competed": {
                    "all": {"2009": 7.125, "2010": 6.9375},
                    "measure": {"2009": 7.125, "2010": 6.9375}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 7.1963, "2010": 7.0069},
                    "efficient": {"2009": 5.1813, "2010": 5.0449}},
                "competed": {
                    "baseline": {"2009": 7.1963, "2010": 7.0069},
                    "efficient": {"2009": 5.1813, "2010": 5.0449}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 406.7016, "2010": 384.801},
                    "efficient": {"2009": 292.8251, "2010": 277.0567}},
                "competed": {
                    "baseline": {"2009": 406.7016, "2010": 384.801},
                    "efficient": {"2009": 292.8251, "2010": 277.0567}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 128.25, "2010": 124.875},
                        "efficient": {"2009": 178.125, "2010": 173.4375}},
                    "competed": {
                        "baseline": {"2009": 128.25, "2010": 124.875},
                        "efficient": {"2009": 178.125, "2010": 173.4375}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 81.1737, "2010": 75.53411},
                        "efficient": {"2009": 58.44506, "2010": 54.38456}},
                    "competed": {
                        "baseline": {"2009": 81.1737, "2010": 75.53411},
                        "efficient": {"2009": 58.44506, "2010": 54.38456}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 13421.15, "2010": 12698.43},
                        "efficient": {"2009": 9663.23, "2010": 9142.871}},
                    "competed": {
                        "baseline": {"2009": 13421.15, "2010": 12698.43},
                        "efficient": {"2009": 9663.23, "2010": 9142.871}}}},
            "lifetime": {"baseline": {"2009": 180, "2010": 180},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 70.3, "2010": 68.45},
                    "measure": {"2009": 70.3, "2010": 68.45}},
                "competed": {
                    "all": {"2009": 70.3, "2010": 68.45},
                    "measure": {"2009": 70.3, "2010": 68.45}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 364.1716, "2010": 355.6422},
                    "efficient": {"2009": 307.7211, "2010": 300.5098}},
                "competed": {
                    "baseline": {"2009": 364.1716, "2010": 355.6422},
                    "efficient": {"2009": 307.7211, "2010": 300.5098}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 20695.84, "2010": 19952.88},
                    "efficient": {"2009": 17487.31, "2010": 16858.09}},
                "competed": {
                    "baseline": {"2009": 20695.84, "2010": 19952.88},
                    "efficient": {"2009": 17487.31, "2010": 16858.09}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 1411.7, "2010": 1374.55},
                        "efficient": {"2009": 1757.5, "2010": 1711.25}},
                    "competed": {
                        "baseline": {"2009": 1411.7, "2010": 1374.55},
                        "efficient": {"2009": 1757.5, "2010": 1711.25}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 3714.15, "2010": 3459.40},
                        "efficient": {"2009": 3139.96, "2010": 2924.58}},
                    "competed": {
                        "baseline": {"2009": 3714.15, "2010": 3459.40},
                        "efficient": {"2009": 3139.96, "2010": 2924.58}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 682962.67, "2010": 658445.18},
                        "efficient": {"2009": 577081.35, "2010": 556317.05}},
                    "competed": {
                        "baseline": {"2009": 682962.67, "2010": 658445.18},
                        "efficient": {"2009": 577081.35, "2010": 556317.05}}}},
            "lifetime": {"baseline": {"2009": 200.81, "2010": 200.81},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 11000000, "2010": 11000000}},
                "competed": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 11000000, "2010": 11000000}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 114.84, "2010": 115.2},
                    "efficient": {"2009": 86.13, "2010": 86.4}},
                "competed": {
                    "baseline": {"2009": 114.84, "2010": 115.2},
                    "efficient": {"2009": 86.13, "2010": 86.4}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 6528.313, "2010": 6470.58},
                    "efficient": {"2009": 4896.234, "2010": 4852.935}},
                "competed": {
                    "baseline": {"2009": 6528.313, "2010": 6470.58},
                    "efficient": {"2009": 4896.234, "2010": 4852.935}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 0, "2010": 0},
                        "efficient": {"2009": 275000000, "2010": 275000000}},
                    "competed": {
                        "baseline": {"2009": 0, "2010": 0},
                        "efficient": {"2009": 275000000, "2010": 275000000}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 1042.747, "2010": 984.96},
                        "efficient": {"2009": 782.0604, "2010": 738.72}},
                    "competed": {
                        "baseline": {"2009": 1042.747, "2010": 984.96},
                        "efficient": {"2009": 782.0604, "2010": 738.72}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 215434.31, "2010": 213529.15},
                        "efficient": {"2009": 161575.74, "2010": 160146.86}},
                    "competed": {
                        "baseline": {"2009": 215434.31, "2010": 213529.15},
                        "efficient": {"2009": 161575.74, "2010": 160146.86}}}},
            "lifetime": {"baseline": {"2009": 10, "2010": 10},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 729, "2010": 729},
                    "measure": {"2009": 729, "2010": 729}},
                "competed": {
                    "all": {"2009": 729, "2010": 729},
                    "measure": {"2009": 729, "2010": 729}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 1177.11, "2010": 1180.8},
                    "efficient": {"2009": 588.555, "2010": 590.4}},
                "competed": {
                    "baseline": {"2009": 1177.11, "2010": 1180.8},
                    "efficient": {"2009": 588.555, "2010": 590.4}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 66915.2, "2010": 66323.45},
                    "efficient": {"2009": 33457.6, "2010": 33161.72}},
                "competed": {
                    "baseline": {"2009": 66915.2, "2010": 66323.45},
                    "efficient": {"2009": 33457.6, "2010": 33161.72}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 0, "2010": 0},
                        "efficient": {"2009": 18225, "2010": 18225}},
                    "competed": {
                        "baseline": {"2009": 0, "2010": 0},
                        "efficient": {"2009": 18225, "2010": 18225}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 11935.9, "2010": 11418.34},
                        "efficient": {"2009": 5967.948, "2010": 5709.168}},
                    "competed": {
                        "baseline": {"2009": 11935.9, "2010": 11418.34},
                        "efficient": {"2009": 5967.948, "2010": 5709.168}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 2208201.73, "2010": 2188673.79},
                        "efficient": {"2009": 1104100.86, "2010": 1094336.90}},
                    "competed": {
                        "baseline": {"2009": 2208201.73, "2010": 2188673.79},
                        "efficient": {"2009": 1104100.86, "2010": 1094336.90}}}
                        },
            "lifetime": {"baseline": {"2009": 10, "2010": 10},
                         "measure": 1}}]
        cls.ok_mapmas_partchck_msegout = [{
            "stock": {
                "total": {
                    "all": {"2009": 11000000, "2010": 11000000},
                    "measure": {"2009": 298571.43, "2010": 597142.86}},
                "competed": {
                    "all": {"2009": 298571.43, "2010": 597142.86},
                    "measure": {"2009": 298571.43, "2010": 597142.86}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 31.90, "2010": 32.00},
                    "efficient": {"2009": 31.52, "2010": 31.24}},
                "competed": {
                    "baseline": {"2009": 0.87, "2010": 1.74},
                    "efficient": {"2009": 0.48, "2010": 0.97}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 1813.42, "2010": 1797.38},
                    "efficient": {"2009": 1791.76, "2010": 1754.45}},
                "competed": {
                    "baseline": {"2009": 49.22, "2010": 97.57},
                    "efficient": {"2009": 27.56, "2010": 54.64}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 154000000, "2010": 154000000},
                        "efficient": {
                            "2009": 157284285.71, "2010": 160568571.42857143}},
                    "competed": {
                        "baseline": {"2009": 4180000, "2010": 8360000},
                        "efficient": {
                            "2009": 7464285.71, "2010": 14928571.43}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 289.65, "2010": 273.60},
                        "efficient": {"2009": 286.19, "2010": 267.06}},
                    "competed": {
                        "baseline": {"2009": 7.86, "2010": 14.85},
                        "efficient": {"2009": 4.40, "2010": 8.32}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 59842.87, "2010": 59313.65},
                        "efficient": {"2009": 59128.17, "2010": 57896.90}},
                    "competed": {
                        "baseline": {"2009": 1624.31, "2010": 3219.88},
                        "efficient": {"2009": 909.61, "2010": 1803.14}}}},
            "lifetime": {"baseline": {"2009": 140, "2010": 140},
                         "measure": 1}}]
        cls.ok_distmeas_out = [
            [120.86, 100, 1741.32, 100, 1.0, 1],
            [11.9, 100, 374.73, 100, 0.93, 100],
            [55.44, 100, 6426946929.70, 100, 1.0, 1]]
        cls.ok_partialmeas_out = [{
            "stock": {
                "total": {
                    "all": {"2009": 18, "2010": 18},
                    "measure": {"2009": 18, "2010": 18}},
                "competed": {
                    "all": {"2009": 18, "2010": 18},
                    "measure": {"2009": 18, "2010": 18}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 57.42, "2010": 57.6},
                    "efficient": {"2009": 27.5616, "2010": 27.648}},
                "competed": {
                    "baseline": {"2009": 57.42, "2010": 57.6},
                    "efficient": {"2009": 27.5616, "2010": 27.648}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 3264.156, "2010": 3235.29},
                    "efficient": {"2009": 1566.795, "2010": 1552.939}},
                "competed": {
                    "baseline": {"2009": 3264.156, "2010": 3235.29},
                    "efficient": {"2009": 1566.795, "2010": 1552.939}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 216, "2010": 216},
                        "efficient": {"2009": 450, "2010": 450}},
                    "competed": {
                        "baseline": {"2009": 216, "2010": 216},
                        "efficient": {"2009": 450, "2010": 450}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 582.2388, "2010": 556.992},
                        "efficient": {"2009": 279.4746, "2010": 267.3562}},
                    "competed": {
                        "baseline": {"2009": 582.2388, "2010": 556.992},
                        "efficient": {"2009": 279.4746, "2010": 267.3562}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 107717.16, "2010": 106764.58},
                        "efficient": {"2009": 51704.24, "2010": 51247}},
                    "competed": {
                        "baseline": {"2009": 107717.16, "2010": 106764.58},
                        "efficient": {"2009": 51704.24, "2010": 51247}}}},
            "lifetime": {"baseline": {"2009": 120, "2010": 120},
                         "measure": 1}},
            {
            "stock": {
                "total": {
                    "all": {"2009": 52, "2010": 52},
                    "measure": {"2009": 52, "2010": 52}},
                "competed": {
                    "all": {"2009": 52, "2010": 52},
                    "measure": {"2009": 52, "2010": 52}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 165.88, "2010": 166.4},
                    "efficient": {"2009": 67.1176, "2010": 67.328}},
                "competed": {
                    "baseline": {"2009": 165.88, "2010": 166.4},
                    "efficient": {"2009": 67.1176, "2010": 67.328}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 9429.785, "2010": 9346.394},
                    "efficient": {"2009": 3815.436, "2010": 3781.695}},
                "competed": {
                    "baseline": {"2009": 9429.785, "2010": 9346.394},
                    "efficient": {"2009": 3815.436, "2010": 3781.695}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 526, "2010": 526},
                        "efficient": {"2009": 1300, "2010": 1300}},
                    "competed": {
                        "baseline": {"2009": 526, "2010": 526},
                        "efficient": {"2009": 1300, "2010": 1300}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 1682.023, "2010": 1609.088},
                        "efficient": {"2009": 680.5725, "2010": 651.0618}},
                    "competed": {
                        "baseline": {"2009": 1682.023, "2010": 1609.088},
                        "efficient": {"2009": 680.5725, "2010": 651.0618}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 311182.9, "2010": 308431},
                        "efficient": {"2009": 125909.39, "2010": 124795.93}},
                    "competed": {
                        "baseline": {"2009": 311182.9, "2010": 308431},
                        "efficient": {"2009": 125909.39, "2010": 124795.93}}}},
            "lifetime": {"baseline": {"2009": 101.1538, "2010": 101.1538},
                         "measure": 1}}]
        cls.ok_warnmeas_out = [
            [("WARNING: 'warn measure 1' has invalid "
              "sub-market scaling fraction source title, author, "
              "organization, and/or year information"),
             ("WARNING: 'warn measure 1' has invalid "
              "sub-market scaling fraction source URL information"),
             ("WARNING: 'warn measure 1' has invalid "
              "sub-market scaling fraction derivation information"),
             ("WARNING (CRITICAL): 'warn measure 1' has "
              "insufficient sub-market source information and "
              "will be removed from analysis")],
            [("WARNING: 'warn measure 2' has invalid "
              "sub-market scaling fraction source URL information"),
             ("WARNING: 'warn measure 2' has invalid "
              "sub-market scaling fraction derivation information"),
             ("WARNING (CRITICAL): 'warn measure 2' has "
              "insufficient sub-market source information and "
              "will be removed from analysis")],
            [("WARNING: 'warn measure 3' has invalid "
              "sub-market scaling fraction source title, author, "
              "organization, and/or year information")]]

    def test_mseg_ok_full_tp(self):
        """Test 'fill_mkts' function given valid inputs.

        Notes:
            Checks the all branches of measure 'markets' attribute
            under a Technical potential scenario.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Run function on all measure objects and check output
        for idx, measure in enumerate(self.ok_tpmeas_fullchk_in):
            measure.fill_mkts(self.sample_mseg_in, self.sample_cpl_in,
                              self.convert_data, self.verbose)
            # Restrict the full check of all branches of 'markets' to only
            # the first three measures in this set. For the remaining two
            # measures, only check the competed choice parameter outputs.
            # These last two measures are intended to test a special case where
            # measure cost units are in $/ft^2 floor rather than $/unit and
            # competed choice parameters must be scaled accordingly
            if idx < 3:
                self.dict_check(
                    measure.markets['Technical potential']['master_mseg'],
                    self.ok_tpmeas_fullchk_msegout[idx])
                self.dict_check(
                    measure.markets['Technical potential']['mseg_adjust'][
                        'secondary mseg adjustments'],
                    self.ok_tpmeas_fullchk_msegadjout[idx])
                self.dict_check(
                    measure.markets['Technical potential']['mseg_out_break'],
                    self.ok_tpmeas_fullchk_break_out[idx])
            self.dict_check(
                measure.markets['Technical potential']['mseg_adjust'][
                    'competed choice parameters'],
                self.ok_tpmeas_fullchk_competechoiceout[idx])

    def test_mseg_ok_part_tp(self):
        """Test 'fill_mkts' function given valid inputs.

        Notes:
            Checks the 'master_mseg' branch of measure 'markets' attribute
            under a Technical potential scenario.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        for idx, measure in enumerate(self.ok_tpmeas_partchk_in):
            measure.fill_mkts(self.sample_mseg_in, self.sample_cpl_in,
                              self.convert_data, self.verbose)
            self.dict_check(
                measure.markets['Technical potential']['master_mseg'],
                self.ok_tpmeas_partchk_msegout[idx])

    def test_mseg_ok_part_map(self):
        """Test 'fill_mkts' function given valid inputs.

        Notes:
            Checks the 'master_mseg' branch of measure 'markets' attribute
            under a Max adoption potential scenario.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Run function on all measure objects and check for correct
        # output
        for idx, measure in enumerate(self.ok_mapmeas_partchk_in):
            measure.fill_mkts(self.sample_mseg_in, self.sample_cpl_in,
                              self.convert_data, self.verbose)
            self.dict_check(
                measure.markets['Max adoption potential']['master_mseg'],
                self.ok_mapmas_partchck_msegout[idx])

    def test_mseg_ok_distrib(self):
        """Test 'fill_mkts' function given valid inputs.

        Notes:
            Valid input measures are assigned distributions on
            their cost, performance, and/or lifetime attributes.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Seed random number generator to yield repeatable results
        numpy.random.seed(1234)
        for idx, measure in enumerate(self.ok_distmeas_in):
            # Generate lists of energy and cost output values
            measure.fill_mkts(
                self.sample_mseg_in, self.sample_cpl_in,
                self.convert_data, self.verbose)
            test_outputs = measure.markets[
                'Technical potential']['master_mseg']
            test_e = test_outputs["energy"]["total"]["efficient"]["2009"]
            test_c = test_outputs[
                "cost"]["stock"]["total"]["efficient"]["2009"]
            test_l = test_outputs["lifetime"]["measure"]
            if type(test_l) == float:
                test_l = [test_l]
            # Calculate mean values from output lists for testing
            param_e = round(sum(test_e) / len(test_e), 2)
            param_c = round(sum(test_c) / len(test_c), 2)
            param_l = round(sum(test_l) / len(test_l), 2)
            # Check mean values and length of output lists to ensure
            # correct
            self.assertEqual([
                param_e, len(test_e), param_c, len(test_c),
                param_l, len(test_l)], self.ok_distmeas_out[idx])

    def test_mseg_partial(self):
        """Test 'fill_mkts' function given partially valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Run function on all measure objects and check output
        for idx, measure in enumerate(self.ok_partialmeas_in):
            measure.fill_mkts(self.sample_mseg_in, self.sample_cpl_in,
                              self.convert_data, self.verbose)
            self.dict_check(
                measure.markets['Technical potential']['master_mseg'],
                self.ok_partialmeas_out[idx])

    def test_mseg_fail_inputs(self):
        """Test 'fill_mkts' function given invalid inputs.

        Raises:
            AssertionError: If ValueError is not raised.
        """
        # Run function on all measure objects and check output
        for idx, measure in enumerate(self.failmeas_inputs_in):
            with self.assertRaises(ValueError):
                measure.fill_mkts(self.sample_mseg_in, self.sample_cpl_in,
                                  self.convert_data, self.verbose)

    def test_mseg_fail_missing(self):
        """Test 'fill_mkts' function given a measure with missing baseline data.

        Raises:
            AssertionError: If KeyError is not raised.
        """
        # Run function on all measure objects and check output
        with self.assertRaises(KeyError):
            self.failmeas_missing_in.fill_mkts(
                self.sample_mseg_in, self.sample_cpl_in,
                self.convert_data, self.verbose)

    def test_mseg_warn(self):
        """Test 'fill_mkts' function given incomplete inputs.

        Raises:
            AssertionError: If function yields unexpected results or
            UserWarning is not raised.
        """
        # Run function on all measure objects and check output
        for idx, mw in enumerate(self.warnmeas_in):
            # Assert that inputs generate correct warnings and that measure
            # is marked inactive where necessary
            with warnings.catch_warnings(record=True) as w:
                mw.fill_mkts(self.sample_mseg_in, self.sample_cpl_in,
                             self.convert_data, self.verbose)
                # Check correct number of warnings is yielded
                self.assertEqual(len(w), len(self.ok_warnmeas_out[idx]))
                # Check correct type of warnings is yielded
                self.assertTrue(all([
                    issubclass(wn.category, UserWarning) for wn in w]))
                [self.assertTrue(wm in str([wmt.message for wmt in w])) for
                    wm in self.ok_warnmeas_out[idx]]
                # Check that measure is marked inactive when a critical
                # warning message is yielded
                if any(['CRITICAL' in x for x in self.ok_warnmeas_out[
                        idx]]):
                    self.assertTrue(mw.remove is True)
                else:
                    self.assertTrue(mw.remove is False)


class PartitionMicrosegmentTest(unittest.TestCase, CommonMethods):
    """Test the operation of the 'partition_microsegment' function.

    Ensure that the function properly partitions an input microsegment
    to yield the required total, competed, and efficient stock, energy,
    carbon and cost information.

    Attributes:
        time_horizons (list): A series of modeling time horizons to use
            in the various test functions of the class.
        handyvars (object): Global variables to use for the test measure.
        sample_measure_in (dict): Sample measure attributes.
        ok_diffuse_params_in (NoneType): Placeholder for eventual technology
            diffusion parameters to be used in 'adjusted adoption' scenario.
        ok_mskeys_in (list): Sample key chains associated with the market
            microsegment being partitioned by the function.
        ok_mkt_scale_frac_in (float): Sample market microsegment scaling
            factor.
        ok_newbldg_frac_in (list): Sample fraction of the total stock that
            is new construction, by year.
        ok_stock_in (list): Sample baseline microsegment stock data, by year.
        ok_energy_in (list): Sample baseline microsegment energy data, by year.
        ok_carb_in (list): Sample baseline microsegment carbon data, by year.
        ok_base_cost_in (list): Sample baseline technology unit costs, by year.
        ok_cost_meas_in (list): Sample measure unit costs.
        ok_cost_energy_base_in (numpy.ndarray): Sample baseline fuel costs.
        ok_cost_energy_meas_in (numpy.ndarray): Sample measure fuel costs.
        ok_relperf_in (list): Sample measure relative performance values.
        ok_life_base_in (dict): Sample baseline technology lifetimes, by year.
        ok_life_meas_in (int): Sample measure lifetime.
        ok_ssconv_base_in (numpy.ndarray): Sample baseline fuel site-source
            conversions, by year.
        ok_ssconv_meas_in (numpy.ndarray): Sample measure fuel site-source
            conversions, by year.
        ok_carbint_base_in (numpy.ndarray): Sample baseline fuel carbon
            intensities, by year.
        ok_carbint_meas_in (numpy.ndarray): Sample measure fuel carbon
            intensities, by year.
        ok_out (list): Outputs that should be yielded by the function given
            valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        cls.time_horizons = [
            ["2009", "2010", "2011"], ["2025", "2026", "2027"],
            ["2020", "2021", "2022"]]
        # Base directory
        base_dir = os.getcwd()
        cls.handyvars = ecm_prep.UsefulVars(base_dir,
                                            ecm_prep.UsefulInputFiles())
        cls.handyvars.retro_rate = 0.02
        cls.handyvars.ccosts = numpy.array(
            (b'Test', 1, 4, 1, 1, 1, 1, 1, 1, 3), dtype=[
                ('Category', 'S11'), ('2009', '<f8'),
                ('2010', '<f8'), ('2011', '<f8'),
                ('2020', '<f8'), ('2021', '<f8'),
                ('2022', '<f8'), ('2025', '<f8'),
                ('2026', '<f8'), ('2027', '<f8')])
        sample_measure_in = {
            "name": "sample measure 1",
            "active": 1,
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": ["single family home"],
            "fuel_type": {
                "primary": ["electricity"],
                "secondary": None},
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["heating", "cooling"],
                "secondary": None},
            "technology": {
                "primary": ["resistance heat", "ASHP", "GSHP", "room AC"],
                "secondary": None}}
        cls.measure_instance = ecm_prep.Measure(
            cls.handyvars, **sample_measure_in)
        cls.ok_diffuse_params_in = None
        cls.ok_mskeys_in = [
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'resistance heat',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'resistance heat',
             'existing')]
        cls.ok_mkt_scale_frac_in = 1
        cls.ok_new_bldg_constr = [{
            "annual new": {"2009": 10, "2010": 5, "2011": 10},
            "total new": {"2009": 10, "2010": 15, "2011": 25}},
            {
            "annual new": {"2025": 10, "2026": 5, "2027": 10},
            "total new": {"2025": 10, "2026": 15, "2027": 25}},
            {
            "annual new": {"2020": 10, "2021": 95, "2022": 10},
            "total new": {"2020": 10, "2021": 100, "2022": 100}}]
        cls.ok_stock_in = [
            {"2009": 100, "2010": 200, "2011": 300},
            {"2025": 400, "2026": 500, "2027": 600},
            {"2020": 700, "2021": 800, "2022": 900}]
        cls.ok_energy_scnd_in = [
            {"2009": 10, "2010": 20, "2011": 30},
            {"2025": 40, "2026": 50, "2027": 60},
            {"2020": 70, "2021": 80, "2022": 90}]
        cls.ok_energy_in = [
            {"2009": 10, "2010": 20, "2011": 30},
            {"2025": 40, "2026": 50, "2027": 60},
            {"2020": 70, "2021": 80, "2022": 90}]
        cls.ok_carb_in = [
            {"2009": 30, "2010": 60, "2011": 90},
            {"2025": 120, "2026": 150, "2027": 180},
            {"2020": 210, "2021": 240, "2022": 270}]
        cls.ok_base_cost_in = [
            {"2009": 10, "2010": 10, "2011": 10},
            {"2025": 20, "2026": 20, "2027": 20},
            {"2020": 30, "2021": 30, "2022": 30}]
        cls.ok_cost_meas_in = [20, 30, 40]
        cls.ok_cost_energy_base_in, cls.ok_cost_energy_meas_in = \
            (numpy.array((b'Test', 1, 2, 2, 2, 2, 2, 2, 2, 2),
                         dtype=[('Category', 'S11'), ('2009', '<f8'),
                                ('2010', '<f8'), ('2011', '<f8'),
                                ('2020', '<f8'), ('2021', '<f8'),
                                ('2022', '<f8'), ('2025', '<f8'),
                                ('2026', '<f8'), ('2027', '<f8')])
             for n in range(2))
        cls.ok_relperf_in = [
            {"2009": 0.30, "2010": 0.30, "2011": 0.30},
            {"2025": 0.15, "2026": 0.15, "2027": 0.15},
            {"2020": 0.75, "2021": 0.75, "2022": 0.75}]
        cls.ok_life_base_in = {
            "2009": 10, "2010": 10, "2011": 10,
            "2020": 10, "2021": 10, "2022": 10,
            "2025": 10, "2026": 10, "2027": 10}
        cls.ok_life_meas_in = 10
        cls.ok_ssconv_base_in, cls.ok_ssconv_meas_in = \
            (numpy.array((b'Test', 1, 1, 1, 1, 1, 1, 1, 1, 1),
                         dtype=[('Category', 'S11'), ('2009', '<f8'),
                                ('2010', '<f8'), ('2011', '<f8'),
                                ('2020', '<f8'), ('2021', '<f8'),
                                ('2022', '<f8'), ('2025', '<f8'),
                                ('2026', '<f8'), ('2027', '<f8')])
             for n in range(2))
        cls.ok_carbint_base_in, cls.ok_carbint_meas_in = \
            (numpy.array((b'Test', 1, 1, 1, 1, 1, 1, 1, 1, 1),
                         dtype=[('Category', 'S11'), ('2009', '<f8'),
                                ('2010', '<f8'), ('2011', '<f8'),
                                ('2020', '<f8'), ('2021', '<f8'),
                                ('2022', '<f8'), ('2025', '<f8'),
                                ('2026', '<f8'), ('2027', '<f8')])
             for n in range(2))
        cls.ok_out = [
            [[[
                {"2009": 100, "2010": 200, "2011": 300},
                {"2009": 10, "2010": 20, "2011": 30},
                {"2009": 30, "2010": 60, "2011": 90},
                {"2009": 100, "2010": 200, "2011": 300},
                {"2009": 3, "2010": 6, "2011": 9},
                {"2009": 9, "2010": 18, "2011": 27},
                {"2009": 100, "2010": 66.67, "2011": 120},
                {"2009": 10, "2010": 6.67, "2011": 12},
                {"2009": 30, "2010": 20, "2011": 36},
                {"2009": 100, "2010": 66.67, "2011": 120},
                {"2009": 3, "2010": 2, "2011": 3.6},
                {"2009": 9, "2010": 6, "2011": 10.8},
                {"2009": 1000, "2010": 2000, "2011": 3000},
                {"2009": 10, "2010": 40, "2011": 60},
                {"2009": 30, "2010": 240, "2011": 90},
                {"2009": 2000, "2010": 4000, "2011": 6000},
                {"2009": 3, "2010": 12, "2011": 18},
                {"2009": 9, "2010": 72, "2011": 27},
                {"2009": 1000, "2010": 666.67, "2011": 1200},
                {"2009": 10, "2010": 13.33, "2011": 24},
                {"2009": 30, "2010": 80, "2011": 36},
                {"2009": 2000, "2010": 1333.33, "2011": 2400},
                {"2009": 3, "2010": 4, "2011": 7.2},
                {"2009": 9, "2010": 24, "2011": 10.8}],
                [
                {"2009": 100, "2010": 200, "2011": 300},
                {"2009": 10, "2010": 20, "2011": 30},
                {"2009": 30, "2010": 60, "2011": 90},
                {"2009": 100, "2010": 200, "2011": 300},
                {"2009": 3, "2010": 6, "2011": 9},
                {"2009": 9, "2010": 18, "2011": 27},
                {"2009": 100, "2010": 0, "2011": 0},
                {"2009": 10, "2010": 0, "2011": 0},
                {"2009": 30, "2010": 0, "2011": 0},
                {"2009": 100, "2010": 0, "2011": 0},
                {"2009": 3, "2010": 0, "2011": 0},
                {"2009": 9, "2010": 0, "2011": 0},
                {"2009": 1000, "2010": 2000, "2011": 3000},
                {"2009": 10, "2010": 40, "2011": 60},
                {"2009": 30, "2010": 240, "2011": 90},
                {"2009": 2000, "2010": 4000, "2011": 6000},
                {"2009": 3, "2010": 12, "2011": 18},
                {"2009": 9, "2010": 72, "2011": 27},
                {"2009": 1000, "2010": 0, "2011": 0},
                {"2009": 10, "2010": 0, "2011": 0},
                {"2009": 30, "2010": 0, "2011": 0},
                {"2009": 2000, "2010": 0, "2011": 0},
                {"2009": 3, "2010": 0, "2011": 0},
                {"2009": 9, "2010": 0, "2011": 0}]],
             [[
                 {"2009": 100, "2010": 200, "2011": 300},
                 {"2009": 10, "2010": 20, "2011": 30},
                 {"2009": 30, "2010": 60, "2011": 90},
                 {"2009": 100, "2010": 166.67, "2011": 286.67},
                 {"2009": 3, "2010": 6, "2011": 9},
                 {"2009": 9, "2010": 18, "2011": 27},
                 {"2009": 100, "2010": 66.67, "2011": 120},
                 {"2009": 10, "2010": 6.67, "2011": 12},
                 {"2009": 30, "2010": 20, "2011": 36},
                 {"2009": 100, "2010": 66.67, "2011": 120},
                 {"2009": 3, "2010": 2, "2011": 3.6},
                 {"2009": 9, "2010": 6, "2011": 10.8},
                 {"2009": 1000, "2010": 2000, "2011": 3000},
                 {"2009": 10, "2010": 40, "2011": 60},
                 {"2009": 30, "2010": 240, "2011": 90},
                 {"2009": 2000, "2010": 3666.67, "2011": 5866.67},
                 {"2009": 3, "2010": 12, "2011": 18},
                 {"2009": 9, "2010": 72, "2011": 27},
                 {"2009": 1000, "2010": 666.67, "2011": 1200},
                 {"2009": 10, "2010": 13.33, "2011": 24},
                 {"2009": 30, "2010": 80, "2011": 36},
                 {"2009": 2000, "2010": 1333.33, "2011": 2400},
                 {"2009": 3, "2010": 4, "2011": 7.2},
                 {"2009": 9, "2010": 24, "2011": 10.8}],
                 [
                 {"2009": 100, "2010": 200, "2011": 300},
                 {"2009": 10, "2010": 20, "2011": 30},
                 {"2009": 30, "2010": 60, "2011": 90},
                 {"2009": 12, "2010": 48, "2011": 108},
                 {"2009": 9.16, "2010": 16.84, "2011": 23.0448},
                 {"2009": 27.48, "2010": 50.52, "2011": 69.1344},
                 {"2009": 12, "2010": 24, "2011": 36},
                 {"2009": 1.2, "2010": 2.4, "2011": 3.6},
                 {"2009": 3.6, "2010": 7.2, "2011": 10.8},
                 {"2009": 12, "2010": 24, "2011": 36},
                 {"2009": 0.36, "2010": 0.72, "2011": 1.08},
                 {"2009": 1.08, "2010": 2.16, "2011": 3.24},
                 {"2009": 1000, "2010": 2000, "2011": 3000},
                 {"2009": 10, "2010": 40, "2011": 60},
                 {"2009": 30, "2010": 240, "2011": 90},
                 {"2009": 1120, "2010": 2480, "2011": 4080},
                 {"2009": 9.16, "2010": 33.68, "2011": 46.0896},
                 {"2009": 27.48, "2010": 202.10, "2011": 69.1344},
                 {"2009": 120, "2010": 240, "2011": 360},
                 {"2009": 1.2, "2010": 4.8, "2011": 7.2},
                 {"2009": 3.6, "2010": 28.8, "2011": 10.8},
                 {"2009": 240, "2010": 480, "2011": 720},
                 {"2009": 0.36, "2010": 1.44, "2011": 2.16},
                 {"2009": 1.08, "2010": 8.64, "2011": 3.24}]]],
            [[[
                {"2025": 400, "2026": 500, "2027": 600},
                {"2025": 40, "2026": 50, "2027": 60},
                {"2025": 120, "2026": 150, "2027": 180},
                {"2025": 400, "2026": 500, "2027": 600},
                {"2025": 6, "2026": 7.5, "2027": 9},
                {"2025": 18, "2026": 22.5, "2027": 27},
                {"2025": 400, "2026": 166.67, "2027": 240},
                {"2025": 40, "2026": 16.67, "2027": 24},
                {"2025": 120, "2026": 50, "2027": 72},
                {"2025": 400, "2026": 166.67, "2027": 240},
                {"2025": 6, "2026": 2.5, "2027": 3.6},
                {"2025": 18, "2026": 7.5, "2027": 10.8},
                {"2025": 8000, "2026": 10000, "2027": 12000},
                {"2025": 80, "2026": 100, "2027": 120},
                {"2025": 120, "2026": 150, "2027": 540},
                {"2025": 12000, "2026": 15000, "2027": 18000},
                {"2025": 12, "2026": 15, "2027": 18},
                {"2025": 18, "2026": 22.5, "2027": 81},
                {"2025": 8000, "2026": 3333.33, "2027": 4800},
                {"2025": 80, "2026": 33.33, "2027": 48},
                {"2025": 120, "2026": 50, "2027": 216},
                {"2025": 12000, "2026": 5000, "2027": 7200},
                {"2025": 12, "2026": 5, "2027": 7.2},
                {"2025": 18, "2026": 7.5, "2027": 32.4}],
                [
                {"2025": 400, "2026": 500, "2027": 600},
                {"2025": 40, "2026": 50, "2027": 60},
                {"2025": 120, "2026": 150, "2027": 180},
                {"2025": 400, "2026": 500, "2027": 600},
                {"2025": 6, "2026": 7.5, "2027": 9},
                {"2025": 18, "2026": 22.5, "2027": 27},
                {"2025": 400, "2026": 0, "2027": 0},
                {"2025": 40, "2026": 0, "2027": 0},
                {"2025": 120, "2026": 0, "2027": 0},
                {"2025": 400, "2026": 0, "2027": 0},
                {"2025": 6, "2026": 0, "2027": 0},
                {"2025": 18, "2026": 0, "2027": 0},
                {"2025": 8000, "2026": 10000, "2027": 12000},
                {"2025": 80, "2026": 100, "2027": 120},
                {"2025": 120, "2026": 150, "2027": 540},
                {"2025": 12000, "2026": 15000, "2027": 18000},
                {"2025": 12, "2026": 15, "2027": 18},
                {"2025": 18, "2026": 22.5, "2027": 81},
                {"2025": 8000, "2026": 0, "2027": 0},
                {"2025": 80, "2026": 0, "2027": 0},
                {"2025": 120, "2026": 0, "2027": 0},
                {"2025": 12000, "2026": 0, "2027": 0},
                {"2025": 12, "2026": 0, "2027": 0},
                {"2025": 18, "2026": 0, "2027": 0}]],
             [[
                 {"2025": 400, "2026": 500, "2027": 600},
                 {"2025": 40, "2026": 50, "2027": 60},
                 {"2025": 120, "2026": 150, "2027": 180},
                 {"2025": 400, "2026": 500, "2027": 600},
                 {"2025": 6, "2026": 7.5, "2027": 9},
                 {"2025": 18, "2026": 22.5, "2027": 27},
                 {"2025": 400, "2026": 166.67, "2027": 240},
                 {"2025": 40, "2026": 16.67, "2027": 24},
                 {"2025": 120, "2026": 50, "2027": 72},
                 {"2025": 400, "2026": 166.67, "2027": 240},
                 {"2025": 6, "2026": 2.5, "2027": 3.6},
                 {"2025": 18, "2026": 7.5, "2027": 10.8},
                 {"2025": 8000, "2026": 10000, "2027": 12000},
                 {"2025": 80, "2026": 100, "2027": 120},
                 {"2025": 120, "2026": 150, "2027": 540},
                 {"2025": 12000, "2026": 15000, "2027": 18000},
                 {"2025": 12, "2026": 15, "2027": 18},
                 {"2025": 18, "2026": 22.5, "2027": 81},
                 {"2025": 8000, "2026": 3333.33, "2027": 4800},
                 {"2025": 80, "2026": 33.33, "2027": 48},
                 {"2025": 120, "2026": 50, "2027": 216},
                 {"2025": 12000, "2026": 5000, "2027": 7200},
                 {"2025": 12, "2026": 5, "2027": 7.2},
                 {"2025": 18, "2026": 7.5, "2027": 32.4}],
                 [
                 {"2025": 400, "2026": 500, "2027": 600},
                 {"2025": 40, "2026": 50, "2027": 60},
                 {"2025": 120, "2026": 150, "2027": 180},
                 {"2025": 48, "2026": 120, "2027": 216},
                 {"2025": 35.92, "2026": 40.41, "2027": 43.1088},
                 {"2025": 107.76, "2026": 121.24, "2027": 129.3264},
                 {"2025": 48, "2026": 60, "2027": 72},
                 {"2025": 4.8, "2026": 6, "2027": 7.2},
                 {"2025": 14.4, "2026": 18.0, "2027": 21.6},
                 {"2025": 48, "2026": 60, "2027": 72},
                 {"2025": 0.72, "2026": 0.90, "2027": 1.08},
                 {"2025": 2.16, "2026": 2.70, "2027": 3.24},
                 {"2025": 8000, "2026": 10000, "2027": 12000},
                 {"2025": 80, "2026": 100, "2027": 120},
                 {"2025": 120, "2026": 150, "2027": 540},
                 {"2025": 8480, "2026": 11200, "2027": 14160},
                 {"2025": 71.84, "2026": 80.82, "2027": 86.2176},
                 {"2025": 107.76, "2026": 121.24, "2027": 387.9792},
                 {"2025": 960, "2026": 1200, "2027": 1440},
                 {"2025": 9.6, "2026": 12.0, "2027": 14.4},
                 {"2025": 14.4, "2026": 18.0, "2027": 64.8},
                 {"2025": 1440, "2026": 1800, "2027": 2160},
                 {"2025": 1.44, "2026": 1.80, "2027": 2.16},
                 {"2025": 2.16, "2026": 2.70, "2027": 9.72}]]],
            [[[
                {"2020": 700, "2021": 800, "2022": 900},
                {"2020": 70, "2021": 80, "2022": 90},
                {"2020": 210, "2021": 240, "2022": 270},
                {"2020": 700, "2021": 800, "2022": 900},
                {"2020": 52.5, "2021": 60, "2022": 67.5},
                {"2020": 157.5, "2021": 180.0, "2022": 202.5},
                {"2020": 700, "2021": 760, "2022": 90},
                {"2020": 70, "2021": 76, "2022": 9},
                {"2020": 210, "2021": 228, "2022": 27},
                {"2020": 700, "2021": 760, "2022": 90},
                {"2020": 52.50, "2021": 57.00, "2022": 6.75},
                {"2020": 157.50, "2021": 171.0, "2022": 20.25},
                {"2020": 21000, "2021": 24000, "2022": 27000},
                {"2020": 140, "2021": 160, "2022": 180},
                {"2020": 210, "2021": 240, "2022": 270},
                {"2020": 28000, "2021": 32000, "2022": 36000},
                {"2020": 105, "2021": 120, "2022": 135},
                {"2020": 157.5, "2021": 180.0, "2022": 202.5},
                {"2020": 21000, "2021": 22800, "2022": 2700},
                {"2020": 140, "2021": 152, "2022": 18.0},
                {"2020": 210, "2021": 228, "2022": 27.0},
                {"2020": 28000, "2021": 30400, "2022": 3600},
                {"2020": 105.0, "2021": 114.0, "2022": 13.5},
                {"2020": 157.50, "2021": 171.00, "2022": 20.25}],
                [
                {"2020": 700, "2021": 800, "2022": 900},
                {"2020": 70, "2021": 80, "2022": 90},
                {"2020": 210, "2021": 240, "2022": 270},
                {"2020": 700, "2021": 800, "2022": 900},
                {"2020": 52.5, "2021": 60, "2022": 67.5},
                {"2020": 157.5, "2021": 180, "2022": 202.5},
                {"2020": 700, "2021": 0, "2022": 0},
                {"2020": 70, "2021": 0, "2022": 0},
                {"2020": 210, "2021": 0, "2022": 0},
                {"2020": 700, "2021": 0, "2022": 0},
                {"2020": 52.5, "2021": 0, "2022": 0},
                {"2020": 157.5, "2021": 0, "2022": 0},
                {"2020": 21000, "2021": 24000, "2022": 27000},
                {"2020": 140, "2021": 160, "2022": 180},
                {"2020": 210, "2021": 240, "2022": 270},
                {"2020": 28000, "2021": 32000, "2022": 36000},
                {"2020": 105, "2021": 120, "2022": 135},
                {"2020": 157.5, "2021": 180.0, "2022": 202.5},
                {"2020": 21000, "2021": 0, "2022": 0},
                {"2020": 140, "2021": 0, "2022": 0},
                {"2020": 210, "2021": 0, "2022": 0},
                {"2020": 28000, "2021": 0, "2022": 0},
                {"2020": 105, "2021": 0, "2022": 0},
                {"2020": 157.5, "2021": 0, "2022": 0}]],
             [[
                 {"2020": 700, "2021": 800, "2022": 900},
                 {"2020": 70, "2021": 80, "2022": 90},
                 {"2020": 210, "2021": 240, "2022": 270},
                 {"2020": 700, "2021": 800, "2022": 890},
                 {"2020": 52.5, "2021": 60, "2022": 67.5},
                 {"2020": 157.5, "2021": 180.0, "2022": 202.5},
                 {"2020": 700, "2021": 760, "2022": 90},
                 {"2020": 70, "2021": 76, "2022": 9},
                 {"2020": 210, "2021": 228, "2022": 27},
                 {"2020": 700, "2021": 760, "2022": 90},
                 {"2020": 52.50, "2021": 57.00, "2022": 6.75},
                 {"2020": 157.50, "2021": 171.0, "2022": 20.25},
                 {"2020": 21000, "2021": 24000, "2022": 27000},
                 {"2020": 140, "2021": 160, "2022": 180},
                 {"2020": 210, "2021": 240, "2022": 270},
                 {"2020": 28000, "2021": 32000, "2022": 35900},
                 {"2020": 105, "2021": 120, "2022": 135},
                 {"2020": 157.5, "2021": 180.0, "2022": 202.5},
                 {"2020": 21000, "2021": 22800, "2022": 2700},
                 {"2020": 140, "2021": 152, "2022": 18.0},
                 {"2020": 210, "2021": 228, "2022": 27.0},
                 {"2020": 28000, "2021": 30400, "2022": 3600},
                 {"2020": 105.0, "2021": 114.0, "2022": 13.5},
                 {"2020": 157.50, "2021": 171.00, "2022": 20.25}],
                 [
                 {"2020": 700, "2021": 800, "2022": 900},
                 {"2020": 70, "2021": 80, "2022": 90},
                 {"2020": 210, "2021": 240, "2022": 270},
                 {"2020": 84, "2021": 192, "2022": 324},
                 {"2020": 67.90, "2021": 75.49, "2022": 82.548},
                 {"2020": 203.70, "2021": 226.46, "2022": 247.644},
                 {"2020": 84, "2021": 96, "2022": 108},
                 {"2020": 8.4, "2021": 9.6, "2022": 10.8},
                 {"2020": 25.2, "2021": 28.8, "2022": 32.4},
                 {"2020": 84, "2021": 96, "2022": 108},
                 {"2020": 6.3, "2021": 7.2, "2022": 8.1},
                 {"2020": 18.9, "2021": 21.6, "2022": 24.3},
                 {"2020": 21000, "2021": 24000, "2022": 27000},
                 {"2020": 140, "2021": 160, "2022": 180},
                 {"2020": 210, "2021": 240, "2022": 270},
                 {"2020": 21840, "2021": 25920, "2022": 30240},
                 {"2020": 135.8, "2021": 150.98, "2022": 165.096},
                 {"2020": 203.70, "2021": 226.46, "2022": 247.644},
                 {"2020": 2520, "2021": 2880, "2022": 3240},
                 {"2020": 16.8, "2021": 19.2, "2022": 21.6},
                 {"2020": 25.2, "2021": 28.8, "2022": 32.4},
                 {"2020": 3360, "2021": 3840, "2022": 4320},
                 {"2020": 12.6, "2021": 14.4, "2022": 16.2},
                 {"2020": 18.9, "2021": 21.6, "2022": 24.3}]]]]

    def test_ok(self):
        """Test the 'partition_microsegment' function given valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Loop through 'ok_out' elements
        for elem in range(0, len(self.ok_out)):
            # Reset AEO time horizon and market entry/exit years
            self.measure_instance.handyvars.aeo_years = \
                self.time_horizons[elem]
            self.measure_instance.market_entry_year = \
                int(self.time_horizons[elem][0])
            self.measure_instance.market_exit_year = \
                int(self.time_horizons[elem][-1]) + 1
            # Loop through two test schemes (Technical potential and Max
            # adoption potential)
            for scn in range(0, len(self.handyvars.adopt_schemes)):
                # Loop through two microsegment key chains (one applying
                # to new structure type, another to existing structure type)
                for k in range(0, len(self.ok_mskeys_in)):
                    # List of output dicts generated by the function
                    lists1 = self.measure_instance.partition_microsegment(
                        self.handyvars.adopt_schemes[scn],
                        self.ok_diffuse_params_in,
                        self.ok_mskeys_in[k],
                        self.ok_mkt_scale_frac_in,
                        self.ok_new_bldg_constr[elem],
                        self.ok_stock_in[elem], self.ok_energy_in[elem],
                        self.ok_carb_in[elem],
                        self.ok_base_cost_in[elem], self.ok_cost_meas_in[elem],
                        self.ok_cost_energy_base_in,
                        self.ok_cost_energy_meas_in,
                        self.ok_relperf_in[elem],
                        self.ok_life_base_in,
                        self.ok_life_meas_in,
                        self.ok_ssconv_base_in, self.ok_ssconv_meas_in,
                        self.ok_carbint_base_in, self.ok_carbint_meas_in,
                        self.ok_energy_scnd_in[elem])
                    # Correct list of output dicts
                    lists2 = self.ok_out[elem][scn][k]
                    # Compare each element of the lists of output dicts
                    for elem2 in range(0, len(lists1)):
                        self.dict_check(lists1[elem2], lists2[elem2])


class CheckMarketsTest(unittest.TestCase, CommonMethods):
    """Test 'check_mkt_inputs' function.

    Ensure that the function properly raises a ValueError when
    a measure's applicable baseline market input names are invalid.

    Attributes:
        sample_measure_fail (dict): Sample measures with applicable
            baseline market input names that should yield an error.
    """

    @classmethod
    def setUpClass(cls):
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measures_fail = [{
            "name": "sample measure 5",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": {
                "primary": 999, "secondary": None},
            "energy_efficiency_units": {
                "primary": "dummy", "secondary": None},
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": "all commercial",
            "structure_type": "all",
            "fuel_type": {
                "primary": [
                    "electricity", "natty gas"],
                "secondary": None},
            "fuel_switch_to": None,
            "end_use": {
                "primary": [
                    "heating", "water heating"],
                "secondary": None},
            "technology": {
                "primary": [
                    "all heating", "electric WH"],
                "secondary": None}},
            {
            "name": "sample measure 6",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": {
                "primary": 999, "secondary": None},
            "energy_efficiency_units": {
                "primary": "dummy", "secondary": None},
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": ["assembling", "education"],
            "structure_type": "all",
            "fuel_type": {
                "primary": "natural gas",
                "secondary": None},
            "fuel_switch_to": None,
            "end_use": {
                "primary": "heating",
                "secondary": None},
            "technology": {
                "primary": "all",
                "secondary": None}}]
        cls.sample_measures_fail = [ecm_prep.Measure(
            handyvars, **x) for x in sample_measures_fail]

    def test_invalid_mkts(self):
        """Test 'check_mkt_inputs' function given invalid inputs."""
        for m in self.sample_measures_fail:
            with self.assertRaises(ValueError):
                m.check_mkt_inputs()


class FillParametersTest(unittest.TestCase, CommonMethods):
    """Test 'fill_attr' function.

    Ensure that the function properly converts user-defined 'all'
    climate zone, building type, fuel type, end use, and technology
    attributes to the expanded set of names needed to retrieve measure
    stock, energy, and technology characteristics data.

    Attributes:
        sample_measure_in (dict): Sample measures with attributes
            including 'all' to fill out.
        ok_primary_cpl_out (list): List of cost, performance, and
            lifetime attributes that should be yielded by the function
            for the first two sample measures, given valid inputs.
        ok_primary_mkts_out (list): List of climate zone, building
            type, primary fuel, primary end use, and primary technology
            attributes that should be yielded by the function for each
            of the sample measures, given valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measures = [{
            "name": "sample measure 1",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": {
                "all residential": 1,
                "all commercial": 2},
            "cost_units": {
                "all residential": "cost unit 1",
                "all commercial": "cost unit 2"},
            "energy_efficiency": {
                "all residential": {
                    "heating": 111, "cooling": 111},
                "all commercial": 222},
            "energy_efficiency_units": {
                "all residential": "energy unit 1",
                "all commercial": "energy unit 2"},
            "product_lifetime": {
                "all residential": 11,
                "all commercial": 22},
            "climate_zone": "all",
            "bldg_type": "all",
            "structure_type": "all",
            "fuel_type": "all",
            "fuel_switch_to": None,
            "end_use": "all",
            "technology": "all"},
            {
            "name": "sample measure 2",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": {
                "all residential": 1,
                "assembly": 2,
                "education": 2},
            "cost_units": {
                "all residential": "cost unit 1",
                "assembly": "cost unit 2",
                "education": "cost unit 2"},
            "energy_efficiency": {
                "all residential": {
                    "heating": 111, "cooling": 111},
                "assembly": 222,
                "education": 222},
            "energy_efficiency_units": {
                "all residential": "energy unit 1",
                "assembly": "energy unit 2",
                "education": "energy unit 2"},
            "product_lifetime": {
                "all residential": 11,
                "assembly": 22,
                "education": 22},
            "climate_zone": "all",
            "bldg_type": [
                "all residential", "assembly", "education"],
            "structure_type": "all",
            "fuel_type": "all",
            "fuel_switch_to": None,
            "end_use": "all",
            "technology": "all"},
            {
            "name": "sample measure 3",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": 999,
            "energy_efficiency_units": "dummy",
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": "all",
            "structure_type": "all",
            "fuel_type": "all",
            "fuel_switch_to": None,
            "end_use": [
                "heating", "cooling", "secondary heating"],
            "technology": "all"},
            {
            "name": "sample measure 4",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": 999,
            "energy_efficiency_units": "dummy",
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": "all residential",
            "structure_type": "all",
            "fuel_type": "electricity",
            "fuel_switch_to": None,
            "end_use": [
                "lighting", "water heating"],
            "technology": "all"},
            {
            "name": "sample measure 5",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": {
                "primary": 999, "secondary": None},
            "energy_efficiency_units": {
                "primary": "dummy", "secondary": None},
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": "all commercial",
            "structure_type": "all",
            "fuel_type": [
                "electricity", "natural gas"],
            "fuel_switch_to": None,
            "end_use": [
                "heating", "water heating"],
            "technology": [
                "all heating", "electric WH"]},
            {
            "name": "sample measure 6",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": 999,
            "energy_efficiency_units": "dummy",
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": ["assembly", "education"],
            "structure_type": "all",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "heating",
            "technology": "all"},
            {
            "name": "sample measure 7",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": 999,
            "energy_efficiency_units": "dummy",
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": [
                "all residential", "small office"],
            "structure_type": "all",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "heating",
            "technology": "all"},
            {
            "name": "sample measure 8",
            "market_entry_year": None,
            "market_exit_year": None,
            "installed_cost": 999,
            "cost_units": "dummy",
            "energy_efficiency": 999,
            "energy_efficiency_units": "dummy",
            "product_lifetime": 999,
            "climate_zone": "all",
            "bldg_type": "small office",
            "structure_type": "all",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "heating",
            "technology": "all"}]
        cls.sample_measures_in = [ecm_prep.Measure(
            handyvars, **x) for x in sample_measures]
        cls.ok_primary_cpl_out = [[{
            'assembly': 2, 'education': 2, 'food sales': 2,
            'food service': 2, 'health care': 2,
            'large office': 2, 'lodging': 2, 'mercantile/service': 2,
            'mobile home': 1, 'multi family home': 1, 'other': 2,
            'single family home': 1, 'small office': 2, 'warehouse': 2},
            {
            'assembly': "cost unit 2", 'education': "cost unit 2",
            'food sales': "cost unit 2",
            'food service': "cost unit 2", 'health care': "cost unit 2",
            'large office': "cost unit 2", 'lodging': "cost unit 2",
            'mercantile/service': "cost unit 2",
            'mobile home': "cost unit 1",
            'multi family home': "cost unit 1", 'other': "cost unit 2",
            'single family home': "cost unit 1",
            'small office': "cost unit 2", 'warehouse': "cost unit 2"},
            {
            'assembly': 222, 'education': 222, 'food sales': 222,
            'food service': 222, 'health care': 222,
            'large office': 222, 'lodging': 222, 'mercantile/service': 222,
            'mobile home': {"heating": 111, "cooling": 111},
            'multi family home': {"heating": 111, "cooling": 111},
            'other': 222,
            'single family home': {"heating": 111, "cooling": 111},
            'small office': 222, 'warehouse': 222},
            {
            'assembly': "energy unit 2", 'education': "energy unit 2",
            'food sales': "energy unit 2",
            'food service': "energy unit 2", 'health care': "energy unit 2",
            'large office': "energy unit 2", 'lodging': "energy unit 2",
            'mercantile/service': "energy unit 2",
            'mobile home': "energy unit 1",
            'multi family home': "energy unit 1", 'other': "energy unit 2",
            'single family home': "energy unit 1",
            'small office': "energy unit 2", 'warehouse': "energy unit 2"},
            {
            'assembly': 22, 'education': 22, 'food sales': 22,
            'food service': 22, 'health care': 22,
            'large office': 22, 'lodging': 22, 'mercantile/service': 22,
            'mobile home': 11, 'multi family home': 11, 'other': 22,
            'single family home': 11, 'small office': 22,
            'warehouse': 22}],
            [{
             'assembly': 2, 'education': 2, 'mobile home': 1,
             'multi family home': 1, 'single family home': 1},
             {
             'assembly': "cost unit 2", 'education': "cost unit 2",
             'mobile home': "cost unit 1", 'multi family home': "cost unit 1",
             'single family home': "cost unit 1"},
             {
             'assembly': 222, 'education': 222,
             'mobile home': {"heating": 111, "cooling": 111},
             'multi family home': {"heating": 111, "cooling": 111},
             'single family home': {"heating": 111, "cooling": 111}},
             {
             'assembly': "energy unit 2", 'education': "energy unit 2",
             'mobile home': "energy unit 1",
             'multi family home': "energy unit 1",
             'single family home': "energy unit 1"},
             {
             'assembly': 22, 'education': 22, 'mobile home': 11,
             'multi family home': 11, 'single family home': 11}]]
        cls.ok_primary_mkts_out = [[
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["single family home", "multi family home", "mobile home",
             "assembly", "education", "food sales", "food service",
             "health care", "lodging", "large office", "small office",
             "mercantile/service", "warehouse", "other"],
            ["new", "existing"],
            ["electricity", "natural gas", "distillate", "other fuel"],
            ['drying', 'other (grid electric)', 'water heating',
             'cooling', 'cooking', 'computers', 'lighting',
             'secondary heating', 'TVs', 'heating', 'refrigeration',
             'fans & pumps', 'ceiling fan', 'ventilation', 'MELs',
             'non-PC office equipment', 'PCs'],
            ['dishwasher', 'other MELs',
             'clothes washing', 'freezers',
             'solar WH', 'electric WH',
             'room AC', 'ASHP', 'GSHP', 'central AC',
             'desktop PC', 'laptop PC', 'network equipment',
             'monitors',
             'linear fluorescent (T-8)',
             'linear fluorescent (T-12)',
             'reflector (LED)', 'general service (CFL)',
             'external (high pressure sodium)',
             'general service (incandescent)',
             'external (CFL)',
             'external (LED)', 'reflector (CFL)',
             'reflector (incandescent)',
             'general service (LED)',
             'external (incandescent)',
             'linear fluorescent (LED)',
             'reflector (halogen)',
             'non-specific',
             'home theater & audio', 'set top box',
             'video game consoles', 'DVD', 'TV',
             'resistance heat',
             'NGHP', 'furnace (NG)', 'boiler (NG)',
             'boiler (distillate)', 'furnace (distillate)',
             'resistance', 'furnace (kerosene)',
             'stove (wood)', 'furnace (LPG)',
             'secondary heating (wood)',
             'secondary heating (coal)',
             'secondary heating (kerosene)',
             'secondary heating (LPG)',
             'VAV_Vent', 'CAV_Vent',
             'Solar water heater', 'HP water heater',
             'elec_booster_water_heater',
             'elec_water_heater',
             'rooftop_AC', 'scroll_chiller',
             'res_type_central_AC', 'reciprocating_chiller',
             'comm_GSHP-cool', 'centrifugal_chiller',
             'rooftop_ASHP-cool', 'wall-window_room_AC',
             'screw_chiller',
             'electric_res-heat', 'comm_GSHP-heat',
             'rooftop_ASHP-heat', 'elec_boiler',
             'Commercial Beverage Merchandisers',
             'Commercial Compressor Rack Systems', 'Commercial Condensers',
             'Commercial Ice Machines', 'Commercial Reach-In Freezers',
             'Commercial Reach-In Refrigerators',
             'Commercial Refrigerated Vending Machines',
             'Commercial Supermarket Display Cases',
             'Commercial Walk-In Freezers',
             'Commercial Walk-In Refrigerators',
             'lab fridges and freezers',
             'non-road electric vehicles',
             'kitchen ventilation', 'escalators',
             'distribution transformers',
             'large video displays', 'video displays',
             'elevators', 'laundry', 'medical imaging',
             'coffee brewers', 'fume hoods',
             'security systems',
             '100W A19 Incandescent', '100W Equivalent A19 Halogen',
             '100W Equivalent CFL Bare Spiral', '100W Equivalent LED A Lamp',
             'Halogen Infrared Reflector (HIR) PAR38', 'Halogen PAR38',
             'LED Integrated Luminaire', 'LED PAR38', 'Mercury Vapor',
             'Metal Halide', 'Sodium Vapor', 'SodiumVapor', 'T5 F28',
             'T5 4xF54 HO High Bay', 'T8 F28 High-efficiency/High-Output',
             'T8 F32 Commodity', 'T8 F59 High Efficiency',
             'T8 F59 Typical Efficiency', 'T8 F96 High Output',
             'Range, Electric-induction, 4 burner, oven, ',
             'Range, Electric, 4 burner, oven, 11 griddle',
             'gas_eng-driven_RTAC', 'gas_chiller',
             'res_type_gasHP-cool',
             'gas_eng-driven_RTHP-cool',
             'gas_water_heater', 'gas_instantaneous_WH',
             'gas_booster_WH',
             'Range, Gas, 4 powered burners, convect. ove',
             'Range, Gas, 4 burner, oven, 11 griddle     ',
             'gas_eng-driven_RTHP-heat',
             'res_type_gasHP-heat', 'gas_boiler',
             'gas_furnace', 'oil_water_heater',
             'oil_boiler', 'oil_furnace', None]],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["single family home", "multi family home", "mobile home",
             "assembly", "education"],
            ["new", "existing"],
            ["electricity", "natural gas", "distillate", "other fuel"],
            ['drying', 'other (grid electric)', 'water heating',
             'cooling', 'cooking', 'computers', 'lighting',
             'secondary heating', 'TVs', 'heating', 'refrigeration',
             'fans & pumps', 'ceiling fan', 'ventilation', 'MELs',
             'non-PC office equipment', 'PCs'],
            ['dishwasher', 'other MELs',
             'clothes washing', 'freezers',
             'solar WH', 'electric WH',
             'room AC', 'ASHP', 'GSHP', 'central AC',
             'desktop PC', 'laptop PC', 'network equipment',
             'monitors',
             'linear fluorescent (T-8)',
             'linear fluorescent (T-12)',
             'reflector (LED)', 'general service (CFL)',
             'external (high pressure sodium)',
             'general service (incandescent)',
             'external (CFL)',
             'external (LED)', 'reflector (CFL)',
             'reflector (incandescent)',
             'general service (LED)',
             'external (incandescent)',
             'linear fluorescent (LED)',
             'reflector (halogen)',
             'non-specific',
             'home theater & audio', 'set top box',
             'video game consoles', 'DVD', 'TV',
             'resistance heat',
             'NGHP', 'furnace (NG)', 'boiler (NG)',
             'boiler (distillate)', 'furnace (distillate)',
             'resistance', 'furnace (kerosene)',
             'stove (wood)', 'furnace (LPG)',
             'secondary heating (wood)',
             'secondary heating (coal)',
             'secondary heating (kerosene)',
             'secondary heating (LPG)',
             'VAV_Vent', 'CAV_Vent',
             'Solar water heater', 'HP water heater',
             'elec_booster_water_heater',
             'elec_water_heater',
             'rooftop_AC', 'scroll_chiller',
             'res_type_central_AC', 'reciprocating_chiller',
             'comm_GSHP-cool', 'centrifugal_chiller',
             'rooftop_ASHP-cool', 'wall-window_room_AC',
             'screw_chiller',
             'electric_res-heat', 'comm_GSHP-heat',
             'rooftop_ASHP-heat', 'elec_boiler',
             'Commercial Beverage Merchandisers',
             'Commercial Compressor Rack Systems', 'Commercial Condensers',
             'Commercial Ice Machines', 'Commercial Reach-In Freezers',
             'Commercial Reach-In Refrigerators',
             'Commercial Refrigerated Vending Machines',
             'Commercial Supermarket Display Cases',
             'Commercial Walk-In Freezers',
             'Commercial Walk-In Refrigerators',
             'lab fridges and freezers',
             'non-road electric vehicles',
             'kitchen ventilation', 'escalators',
             'distribution transformers',
             'large video displays', 'video displays',
             'elevators', 'laundry', 'medical imaging',
             'coffee brewers', 'fume hoods',
             'security systems',
             '100W A19 Incandescent', '100W Equivalent A19 Halogen',
             '100W Equivalent CFL Bare Spiral', '100W Equivalent LED A Lamp',
             'Halogen Infrared Reflector (HIR) PAR38', 'Halogen PAR38',
             'LED Integrated Luminaire', 'LED PAR38', 'Mercury Vapor',
             'Metal Halide', 'Sodium Vapor', 'SodiumVapor', 'T5 F28',
             'T5 4xF54 HO High Bay', 'T8 F28 High-efficiency/High-Output',
             'T8 F32 Commodity', 'T8 F59 High Efficiency',
             'T8 F59 Typical Efficiency', 'T8 F96 High Output',
             'Range, Electric-induction, 4 burner, oven, ',
             'Range, Electric, 4 burner, oven, 11 griddle',
             'gas_eng-driven_RTAC', 'gas_chiller',
             'res_type_gasHP-cool',
             'gas_eng-driven_RTHP-cool',
             'gas_water_heater', 'gas_instantaneous_WH',
             'gas_booster_WH',
             'Range, Gas, 4 powered burners, convect. ove',
             'Range, Gas, 4 burner, oven, 11 griddle     ',
             'gas_eng-driven_RTHP-heat',
             'res_type_gasHP-heat', 'gas_boiler',
             'gas_furnace', 'oil_water_heater',
             'oil_boiler', 'oil_furnace', None]],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["single family home", "multi family home", "mobile home",
             "assembly", "education", "food sales", "food service",
             "health care", "lodging", "large office", "small office",
             "mercantile/service", "warehouse", "other"],
            ["new", "existing"],
            ["electricity", "natural gas", "distillate", "other fuel"],
            ['cooling', 'secondary heating', 'heating'],
            ['rooftop_AC', 'scroll_chiller',
             'res_type_central_AC', 'reciprocating_chiller',
             'comm_GSHP-cool', 'centrifugal_chiller',
             'rooftop_ASHP-cool', 'wall-window_room_AC',
             'screw_chiller', 'electric_res-heat',
             'comm_GSHP-heat', 'rooftop_ASHP-heat', 'elec_boiler',
             'non-specific', 'furnace (NG)', 'boiler (NG)',
             'NGHP', 'room AC', 'ASHP', 'GSHP', 'central AC',
             'resistance heat', 'boiler (distillate)',
             'furnace (distillate)', 'resistance', 'furnace (kerosene)',
             'stove (wood)', 'furnace (LPG)',
             'gas_eng-driven_RTAC', 'gas_chiller',
             'res_type_gasHP-cool', 'gas_eng-driven_RTHP-cool',
             'gas_eng-driven_RTHP-heat', 'res_type_gasHP-heat',
             'gas_boiler', 'gas_furnace', 'oil_boiler', 'oil_furnace',
             'secondary heating (wood)', 'secondary heating (coal)',
             'secondary heating (kerosene)', 'secondary heating (LPG)']],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["single family home", "multi family home", "mobile home"],
            ["new", "existing"], "electricity",
            ["lighting", "water heating"],
            ['solar WH', 'electric WH', 'linear fluorescent (T-8)',
             'linear fluorescent (T-12)',
             'reflector (LED)', 'general service (CFL)',
             'external (high pressure sodium)',
             'general service (incandescent)',
             'external (CFL)',
             'external (LED)', 'reflector (CFL)',
             'reflector (incandescent)',
             'general service (LED)',
             'external (incandescent)',
             'linear fluorescent (LED)',
             'reflector (halogen)']],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["assembly", "education", "food sales", "food service",
             "health care", "lodging", "large office", "small office",
             "mercantile/service", "warehouse", "other"],
            ["new", "existing"],
            ["electricity", "natural gas"],
            ["heating", "water heating"],
            ['electric_res-heat', 'comm_GSHP-heat', 'rooftop_ASHP-heat',
             'elec_boiler', 'gas_eng-driven_RTHP-heat', 'res_type_gasHP-heat',
             'gas_boiler', 'gas_furnace', 'electric WH']],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["assembly", "education"],
            ["new", "existing"], "natural gas", "heating",
            ["res_type_gasHP-heat", "gas_eng-driven_RTHP-heat",
             "gas_boiler", "gas_furnace"]],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            ["single family home", "multi family home", "mobile home",
             "small office"],
            ["new", "existing"], "natural gas", "heating",
            ["furnace (NG)", "NGHP", "boiler (NG)", "res_type_gasHP-heat",
             "gas_eng-driven_RTHP-heat", "gas_boiler", "gas_furnace"]],
            [
            ["AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5"],
            "small office", ["new", "existing"], "natural gas",
            "heating", [
                "res_type_gasHP-heat", "gas_eng-driven_RTHP-heat",
                "gas_boiler", "gas_furnace"]]]

    def test_fill(self):
        """Test 'fill_attr' function given valid inputs.

        Note:
            Tests that measure attributes containing 'all' are properly
            filled in with the appropriate attribute details.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        # Loop through sample measures
        for ind, m in enumerate(self.sample_measures_in):
            # Execute the function on each sample measure
            m.fill_attr()
            # For the first two sample measures, check that cost, performance,
            # and lifetime attribute dicts with 'all residential' and
            # 'all commercial' keys were properly filled out
            if ind < 2:
                [self.dict_check(x, y) for x, y in zip([
                    m.installed_cost, m.cost_units,
                    m.energy_efficiency["primary"],
                    m.energy_efficiency_units["primary"],
                    m.product_lifetime],
                    [o for o in self.ok_primary_cpl_out[ind]])]
            # For each sample measure, check that 'all' climate zone,
            # building type/vintage, fuel type, end use, and technology
            # attributes were properly filled out
            self.assertEqual([
                sorted(x, key=lambda x: (x is None, x)) if isinstance(x, list)
                else x for x in [
                    m.climate_zone, m.bldg_type, m.structure_type,
                    m.fuel_type['primary'], m.end_use['primary'],
                    m.technology['primary']]],
                [sorted(x, key=lambda x: (x is None, x)) if isinstance(x, list)
                 else x for x in self.ok_primary_mkts_out[ind]])


class CreateKeyChainTest(unittest.TestCase, CommonMethods):
    """Test 'create_keychain' function.

    Ensure that the function yields proper key chain output given
    input microsegment information.

    Attributes:
        sample_measure_in (dict): Sample measure attributes.
        ok_out_primary (list): Primary microsegment key chain that should
            be yielded by the function given valid inputs.
        ok_out_secondary (list): Secondary microsegment key chain that
            should be yielded by the function given valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measure = {
            "name": "sample measure 2",
            "active": 1,
            "market_entry_year": None,
            "market_exit_year": None,
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": 0.5,
            "energy_efficiency_units": "relative savings (constant)",
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": "single family home",
            "fuel_type": {
                "primary": "electricity",
                "secondary": "electricity"},
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["heating", "cooling"],
                "secondary": "lighting"},
            "technology": {
                "primary": ["resistance heat", "ASHP", "GSHP", "room AC"],
                "secondary": "general service (LED)"},
            "mseg_adjust": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "sub-market": {
                        "original energy (total)": {},
                        "adjusted energy (sub-market)": {}},
                    "stock-and-flow": {
                        "original energy (total)": {},
                        "adjusted energy (previously captured)": {},
                        "adjusted energy (competed)": {},
                        "adjusted energy (competed and captured)": {}},
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}}}
        cls.sample_measure_in = ecm_prep.Measure(
            handyvars, **sample_measure)
        # Finalize the measure's 'technology_type' attribute (handled by the
        # 'fill_attr' function, which is not run as part of this test)
        cls.sample_measure_in.technology_type = {
            "primary": "supply", "secondary": "supply"}
        cls.ok_out_primary = [
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply',
             'resistance heat', 'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'ASHP',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'GSHP',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'room AC',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply',
             'resistance heat', 'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply', 'ASHP',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply', 'GSHP',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply', 'room AC',
             'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply',
             'resistance heat', 'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply', 'ASHP',
             'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply', 'GSHP',
             'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply', 'room AC',
             'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply',
             'resistance heat', 'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply', 'ASHP',
             'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply', 'GSHP',
             'new'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply', 'room AC',
             'new'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply',
             'resistance heat', 'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'ASHP',
             'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'GSHP',
             'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'heating', 'supply', 'room AC',
             'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply',
             'resistance heat', 'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply', 'ASHP',
             'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply', 'GSHP',
             'existing'),
            ('primary', 'AIA_CZ1', 'single family home',
             'electricity', 'cooling', 'supply', 'room AC',
             'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply',
             'resistance heat', 'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply', 'ASHP',
             'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply', 'GSHP',
             'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'heating', 'supply', 'room AC',
             'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply',
             'resistance heat', 'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply', 'ASHP',
             'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply', 'GSHP',
             'existing'),
            ('primary', 'AIA_CZ2', 'single family home',
             'electricity', 'cooling', 'supply', 'room AC',
             'existing')]
        cls.ok_out_secondary = [
            ('secondary', 'AIA_CZ1', 'single family home',
             'electricity', 'lighting',
             'general service (LED)', 'new'),
            ('secondary', 'AIA_CZ2', 'single family home',
             'electricity', 'lighting',
             'general service (LED)', 'new'),
            ('secondary', 'AIA_CZ1', 'single family home',
             'electricity', 'lighting',
             'general service (LED)', 'existing'),
            ('secondary', 'AIA_CZ2', 'single family home',
             'electricity', 'lighting',
             'general service (LED)', 'existing')]

    def test_primary(self):
        """Test 'create_keychain' function given valid inputs.

        Note:
            Tests generation of primary microsegment key chains.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.assertEqual(
            self.sample_measure_in.create_keychain("primary")[0],
            self.ok_out_primary)

    # Test the generation of a list of secondary mseg key chains
    def test_secondary(self):
        """Test 'create_keychain' function given valid inputs.

        Note:
            Tests generation of secondary microsegment key chains.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.assertEqual(
            self.sample_measure_in.create_keychain("secondary")[0],
            self.ok_out_secondary)


class AddKeyValsTest(unittest.TestCase, CommonMethods):
    """Test 'add_keyvals' and 'add_keyvals_restrict' functions.

    Ensure that the functions properly add together input dictionaries.

    Attributes:
        sample_measure_in (dict): Sample measure attributes.
        ok_dict1_in (dict): Valid sample input dict for 'add_keyvals' function.
        ok_dict2_in (dict): Valid sample input dict for 'add_keyvals' function.
        ok_dict3_in (dict): Valid sample input dict for
            'add_keyvals_restrict' function.
        ok_dict4_in (dict): Valid sample input dict for
            'add_keyvals_restrict' function.
        fail_dict1_in (dict): One of two invalid sample input dicts for
            'add_keyvals' function (dict keys do not exactly match).
        fail_dict2_in (dict): Two of two invalid sample input dicts for
            'add_keyvals' function (dict keys do not exactly match).
        ok_out (dict): Dictionary that should be generated by 'add_keyvals'
            function given valid inputs.
        ok_out_restrict (dict): Dictionary that should be generated by
            'add_keyvals_restrict' function given valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measure_in = {
            "name": "sample measure 1",
            "active": 1,
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": ["single family home"],
            "fuel_type": {
                "primary": ["electricity"],
                "secondary": None},
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["heating", "cooling"],
                "secondary": None},
            "technology": {
                "primary": ["resistance heat", "ASHP", "GSHP", "room AC"],
                "secondary": None}}
        cls.sample_measure_in = ecm_prep.Measure(
            handyvars, **sample_measure_in)
        cls.ok_dict1_in, cls.ok_dict2_in = ({
            "level 1a": {
                "level 2aa": {"2009": 2, "2010": 3},
                "level 2ab": {"2009": 4, "2010": 5}},
            "level 1b": {
                "level 2ba": {"2009": 6, "2010": 7},
                "level 2bb": {"2009": 8, "2010": 9}}} for n in range(2))
        cls.ok_dict3_in, cls.ok_dict4_in = ({
            "level 1a": {
                "level 2aa": {"2009": 2, "2010": 3},
                "level 2ab": {"2009": 4, "2010": 5}},
            "lifetime": {
                "level 2ba": {"2009": 6, "2010": 7},
                "level 2bb": {"2009": 8, "2010": 9}}} for n in range(2))
        cls.fail_dict1_in = {
            "level 1a": {
                "level 2aa": {"2009": 2, "2010": 3},
                "level 2ab": {"2009": 4, "2010": 5}},
            "level 1b": {
                "level 2ba": {"2009": 6, "2010": 7},
                "level 2bb": {"2009": 8, "2010": 9}}}
        cls.fail_dict2_in = {
            "level 1a": {
                "level 2aa": {"2009": 2, "2010": 3},
                "level 2ab": {"2009": 4, "2010": 5}},
            "level 1b": {
                "level 2ba": {"2009": 6, "2010": 7},
                "level 2bb": {"2009": 8, "2011": 9}}}
        cls.ok_out = {
            "level 1a": {
                "level 2aa": {"2009": 4, "2010": 6},
                "level 2ab": {"2009": 8, "2010": 10}},
            "level 1b": {
                "level 2ba": {"2009": 12, "2010": 14},
                "level 2bb": {"2009": 16, "2010": 18}}}
        cls.ok_out_restrict = {
            "level 1a": {
                "level 2aa": {"2009": 4, "2010": 6},
                "level 2ab": {"2009": 8, "2010": 10}},
            "lifetime": {
                "level 2ba": {"2009": 6, "2010": 7},
                "level 2bb": {"2009": 8, "2010": 9}}}

    def test_ok_add_keyvals(self):
        """Test 'add_keyvals' function given valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(
            self.sample_measure_in.add_keyvals(
                self.ok_dict1_in, self.ok_dict2_in), self.ok_out)

    def test_fail_add_keyvals(self):
        """Test 'add_keyvals' function given invalid inputs.

        Raises:
            AssertionError: If KeyError is not raised.
        """
        with self.assertRaises(KeyError):
            self.sample_measure_in.add_keyvals(
                self.fail_dict1_in, self.fail_dict2_in)

    def test_ok_add_keyvals_restrict(self):
        """Test 'add_keyvals_restrict' function given valid inputs."""
        self.dict_check(
            self.sample_measure_in.add_keyvals_restrict(
                self.ok_dict3_in, self.ok_dict4_in), self.ok_out_restrict)


class DivKeyValsTest(unittest.TestCase, CommonMethods):
    """Test 'div_keyvals' function.

    Ensure that the function properly divides the key values of one dict
    by those of another. Test inputs reflect the use of this function
    to generate output partitioning fractions (used to break out
    measure results by climate zone, building sector, end use).

    Attributes:
        sample_measure_in (dict): Sample measure attributes.
        ok_reduce_dict (dict): Values from second dict to normalize first
            dict values by.
        ok_dict_in (dict): Sample input dict with values to normalize.
        ok_out (dict): Output dictionary that should be yielded by the
            function given valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measure_in = {
            "name": "sample measure 1",
            "active": 1,
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": ["single family home"],
            "fuel_type": {
                "primary": ["electricity"],
                "secondary": None},
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["heating", "cooling"],
                "secondary": None},
            "technology": {
                "primary": ["resistance heat", "ASHP", "GSHP", "room AC"],
                "secondary": None}}
        cls.sample_measure_in = ecm_prep.Measure(
            handyvars, **sample_measure_in)
        cls.ok_reduce_dict = {"2009": 100, "2010": 100}
        cls.ok_dict_in = {
            "AIA CZ1": {
                "Residential": {
                    "Heating": {"2009": 10, "2010": 10},
                    "Cooling": {"2009": 15, "2010": 15}},
                "Commercial": {
                    "Heating": {"2009": 20, "2010": 20},
                    "Cooling": {"2009": 25, "2010": 25}}},
            "AIA CZ2": {
                "Residential": {
                    "Heating": {"2009": 30, "2010": 30},
                    "Cooling": {"2009": 35, "2010": 35}},
                "Commercial": {
                    "Heating": {"2009": 40, "2010": 40},
                    "Cooling": {"2009": 45, "2010": 45}}}}
        cls.ok_out = {
            "AIA CZ1": {
                "Residential": {
                    "Heating": {"2009": .10, "2010": .10},
                    "Cooling": {"2009": .15, "2010": .15}},
                "Commercial": {
                    "Heating": {"2009": .20, "2010": .20},
                    "Cooling": {"2009": .25, "2010": .25}}},
            "AIA CZ2": {
                "Residential": {
                    "Heating": {"2009": .30, "2010": .30},
                    "Cooling": {"2009": .35, "2010": .35}},
                "Commercial": {
                    "Heating": {"2009": .40, "2010": .40},
                    "Cooling": {"2009": .45, "2010": .45}}}}

    def test_ok(self):
        """Test 'div_keyvals' function given valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(
            self.sample_measure_in.div_keyvals(
                self.ok_dict_in, self.ok_reduce_dict), self.ok_out)


class DivKeyValsFloatTest(unittest.TestCase, CommonMethods):
    """Test 'div_keyvals_float' and div_keyvals_float_restrict' functions.

    Ensure that the functions properly divide dict key values by a given
    factor.

    Attributes:
        sample_measure_in (dict): Sample measure attributes.
        ok_reduce_num (float): Factor by which dict values should be divided.
        ok_dict_in (dict): Sample input dict with values to divide.
        ok_out (dict): Output dictionary that should be yielded by
            'div_keyvals_float' function given valid inputs.
        ok_out_restrict (dict): Output dictionary that should be yielded by
            'div_keyvals_float_restrict'function given valid inputs.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measure_in = {
            "name": "sample measure 1",
            "active": 1,
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": ["single family home"],
            "fuel_type": {
                "primary": ["electricity"],
                "secondary": None},
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["heating", "cooling"],
                "secondary": None},
            "technology": {
                "primary": ["resistance heat", "ASHP", "GSHP", "room AC"],
                "secondary": None}}
        cls.sample_measure_in = ecm_prep.Measure(
            handyvars, **sample_measure_in)
        cls.ok_reduce_num = 4
        cls.ok_dict_in = {
            "stock": {
                "total": {"2009": 100, "2010": 200},
                "competed": {"2009": 300, "2010": 400}},
            "energy": {
                "total": {"2009": 500, "2010": 600},
                "competed": {"2009": 700, "2010": 800},
                "efficient": {"2009": 700, "2010": 800}},
            "carbon": {
                "total": {"2009": 500, "2010": 600},
                "competed": {"2009": 700, "2010": 800},
                "efficient": {"2009": 700, "2010": 800}},
            "cost": {
                "baseline": {
                    "stock": {"2009": 900, "2010": 1000},
                    "energy": {"2009": 900, "2010": 1000},
                    "carbon": {"2009": 900, "2010": 1000}},
                "measure": {
                    "stock": {"2009": 1100, "2010": 1200},
                    "energy": {"2009": 1100, "2010": 1200},
                    "carbon": {"2009": 1100, "2010": 1200}}}}
        cls.ok_out = {
            "stock": {
                "total": {"2009": 25, "2010": 50},
                "competed": {"2009": 75, "2010": 100}},
            "energy": {
                "total": {"2009": 125, "2010": 150},
                "competed": {"2009": 175, "2010": 200},
                "efficient": {"2009": 175, "2010": 200}},
            "carbon": {
                "total": {"2009": 125, "2010": 150},
                "competed": {"2009": 175, "2010": 200},
                "efficient": {"2009": 175, "2010": 200}},
            "cost": {
                "baseline": {
                    "stock": {"2009": 225, "2010": 250},
                    "energy": {"2009": 225, "2010": 250},
                    "carbon": {"2009": 225, "2010": 250}},
                "measure": {
                    "stock": {"2009": 275, "2010": 300},
                    "energy": {"2009": 275, "2010": 300},
                    "carbon": {"2009": 275, "2010": 300}}}}
        cls.ok_out_restrict = {
            "stock": {
                "total": {"2009": 25, "2010": 50},
                "competed": {"2009": 75, "2010": 100}},
            "energy": {
                "total": {"2009": 500, "2010": 600},
                "competed": {"2009": 700, "2010": 800},
                "efficient": {"2009": 700, "2010": 800}},
            "carbon": {
                "total": {"2009": 500, "2010": 600},
                "competed": {"2009": 700, "2010": 800},
                "efficient": {"2009": 700, "2010": 800}},
            "cost": {
                "baseline": {
                    "stock": {"2009": 225, "2010": 250},
                    "energy": {"2009": 900, "2010": 1000},
                    "carbon": {"2009": 900, "2010": 1000}},
                "measure": {
                    "stock": {"2009": 275, "2010": 300},
                    "energy": {"2009": 1100, "2010": 1200},
                    "carbon": {"2009": 1100, "2010": 1200}}}}

    def test_ok_div(self):
        """Test 'div_keyvals_float' function given valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(
            self.sample_measure_in.div_keyvals_float(
                copy.deepcopy(self.ok_dict_in), self.ok_reduce_num),
            self.ok_out)

    def test_ok_div_restrict(self):
        """Test 'div_keyvals_float_restrict' function given valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.dict_check(
            self.sample_measure_in.div_keyvals_float_restrict(
                copy.deepcopy(self.ok_dict_in), self.ok_reduce_num),
            self.ok_out_restrict)


class AppendKeyValsTest(unittest.TestCase):
    """Test 'append_keyvals' function.

    Ensure that the function properly determines a list of valid names
    for describing a measure's applicable baseline market.

    Attributes:
        handyvars (object): Global variables to use for the test measure.
        ok_mktnames_out (list): Set of valid names that should be generated
            by the function given valid inputs.
    """
    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        base_dir = os.getcwd()
        cls.handyvars = ecm_prep.UsefulVars(base_dir,
                                            ecm_prep.UsefulInputFiles())
        cls.ok_mktnames_out = [
            "AIA_CZ1", "AIA_CZ2", "AIA_CZ3", "AIA_CZ4", "AIA_CZ5",
            "single family home",
            "multi family home", "mobile home",
            "assembly", "education", "food sales", "food service",
            "health care", "lodging", "large office", "small office",
            "mercantile/service", "warehouse", "other",
            "electricity", "natural gas", "distillate", "other fuel",
            'drying', 'other (grid electric)', 'water heating',
            'cooling', 'cooking', 'computers', 'lighting',
            'secondary heating', 'TVs', 'heating', 'refrigeration',
            'fans & pumps', 'ceiling fan', 'ventilation', 'MELs',
            'non-PC office equipment', 'PCs',
            'dishwasher', 'other MELs', 'clothes washing', 'freezers',
            'solar WH', 'electric WH', 'room AC', 'ASHP', 'central AC',
            'desktop PC', 'laptop PC', 'network equipment', 'monitors',
            'linear fluorescent (T-8)', 'linear fluorescent (T-12)',
            'reflector (LED)', 'general service (CFL)',
            'external (high pressure sodium)',
            'general service (incandescent)',
            'external (CFL)', 'external (LED)', 'reflector (CFL)',
            'reflector (incandescent)', 'general service (LED)',
            'external (incandescent)', 'linear fluorescent (LED)',
            'reflector (halogen)', 'non-specific', 'home theater & audio',
            'set top box', 'video game consoles', 'DVD', 'TV',
            'GSHP', 'resistance heat', 'NGHP', 'furnace (NG)',
            'boiler (NG)', 'boiler (distillate)', 'furnace (distillate)',
            'resistance', 'furnace (kerosene)', 'stove (wood)',
            'furnace (LPG)', 'secondary heating (wood)',
            'secondary heating (coal)', 'secondary heating (kerosene)',
            'secondary heating (LPG)', 'roof', 'ground', 'windows solar',
            'windows conduction', 'equipment gain', 'people gain', 'wall',
            'infiltration', 'lighting gain', 'floor', 'other heat gain',
            'VAV_Vent', 'CAV_Vent', 'Solar water heater',
            'HP water heater', 'elec_booster_water_heater',
            'elec_water_heater', 'rooftop_AC', 'scroll_chiller',
            'res_type_central_AC', 'reciprocating_chiller', 'comm_GSHP-cool',
            'centrifugal_chiller', 'rooftop_ASHP-cool', 'wall-window_room_AC',
            'screw_chiller', 'electric_res-heat', 'comm_GSHP-heat',
            'rooftop_ASHP-heat', 'elec_boiler',
            'Commercial Beverage Merchandisers',
            'Commercial Compressor Rack Systems', 'Commercial Condensers',
            'Commercial Ice Machines', 'Commercial Reach-In Freezers',
            'Commercial Reach-In Refrigerators',
            'Commercial Refrigerated Vending Machines',
            'Commercial Supermarket Display Cases',
            'Commercial Walk-In Freezers',
            'Commercial Walk-In Refrigerators',
            'lab fridges and freezers',
            'non-road electric vehicles', 'kitchen ventilation',
            'escalators', 'distribution transformers',
            'large video displays', 'video displays', 'elevators', 'laundry',
            'medical imaging', 'coffee brewers', 'fume hoods',
            'security systems',
            '100W A19 Incandescent', '100W Equivalent A19 Halogen',
            '100W Equivalent CFL Bare Spiral', '100W Equivalent LED A Lamp',
            'Halogen Infrared Reflector (HIR) PAR38', 'Halogen PAR38',
            'LED Integrated Luminaire', 'LED PAR38', 'Mercury Vapor',
            'Metal Halide', 'Sodium Vapor', 'SodiumVapor', 'T5 F28',
            'T5 4xF54 HO High Bay', 'T8 F28 High-efficiency/High-Output',
            'T8 F32 Commodity', 'T8 F59 High Efficiency',
            'T8 F59 Typical Efficiency', 'T8 F96 High Output',
            'Range, Electric-induction, 4 burner, oven, ',
            'Range, Electric, 4 burner, oven, 11 griddle',
            'gas_eng-driven_RTAC', 'gas_chiller', 'res_type_gasHP-cool',
            'gas_eng-driven_RTHP-cool', 'gas_water_heater',
            'gas_instantaneous_WH', 'gas_booster_WH',
            'Range, Gas, 4 powered burners, convect. ove',
            'Range, Gas, 4 burner, oven, 11 griddle     ',
            'gas_eng-driven_RTHP-heat', 'res_type_gasHP-heat',
            'gas_boiler', 'gas_furnace', 'oil_water_heater', 'oil_boiler',
            'oil_furnace', 'new', 'existing', 'supply', 'demand',
            'all', 'all residential', 'all commercial', 'all heating',
            'all drying', 'all other (grid electric)',
            'all water heating', 'all cooling', 'all cooking',
            'all computers', 'all lighting', 'all secondary heating',
            'all TVs', 'all refrigeration', 'all fans & pumps',
            'all ceiling fan', 'all ventilation', 'all MELs',
            'all non-PC office equipment', 'all PCs']

    def test_ok_append(self):
        """Test 'append_keyvals' function given valid inputs.

        Raises:
            AssertionError: If function yields unexpected results.
        """
        self.assertEqual(sorted(
            [x for x in self.handyvars.valid_mktnames if x is not None]),
            sorted([x for x in self.ok_mktnames_out if x is not None]))


class CostConversionTest(unittest.TestCase, CommonMethods):
    """Test 'convert_costs' function.

    Ensure that function properly converts user-defined measure cost units
    to align with comparable baseline cost units.

    Attributes:
        verbose (NoneType): Determines whether to print all user messages.
        sample_measure_in (dict): Sample measure attributes.
        sample_convertdata_ok_in (dict): Sample cost conversion input data.
        sample_bldgsect_ok_in (list): List of valid building sectors for
            sample measure cost.
        sample_mskeys_ok_in (list): List of valid full market microsegment
            information for sample measure cost (mseg type->czone->bldg->fuel->
            end use->technology type->structure type).
        sample_mskeys_fail_in (list): List of microsegment information for
            sample measure cost that should cause function to fail.
        cost_meas_ok_in (int): Sample measure cost.
        cost_meas_units_ok_in_yronly (string): List of valid sample measure
            cost units where only the cost year needs adjustment.
        cost_meas_units_ok_in_all (list): List of valid sample measure cost
            units where the cost year and/or units need adjustment.
        cost_meas_units_fail_in (string): List of sample measure cost units
            that should cause the function to fail.
        cost_base_units_ok_in (string): List of valid baseline cost units.
        ok_out_costs_yronly (float): Converted measure costs that should be
            yielded given 'cost_meas_units_ok_in_yronly' measure cost units.
        ok_out_costs_all (list): Converted measure costs that should be
            yielded given 'cost_meas_units_ok_in_all' measure cost units.
        ok_out_cost_units (string): Converted measure cost units that should
            be yielded given valid inputs to the function.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        sample_measure_in = {
            "name": "sample measure 2",
            "remove": False,
            "market_entry_year": None,
            "market_exit_year": None,
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": 0.5,
            "energy_efficiency_units": "relative savings (constant)",
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": ["single family home"],
            "fuel_type": {
                "primary": ["electricity"],
                "secondary": ["electricity"]},
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["heating", "cooling"],
                "secondary": ["lighting"]},
            "technology": {
                "primary": ["resistance heat", "ASHP", "GSHP", "room AC"],
                "secondary": ["general service (LED)"]},
            "mseg_adjust": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "sub-market": {
                        "original energy (total)": {},
                        "adjusted energy (sub-market)": {}},
                    "stock-and-flow": {
                        "original energy (total)": {},
                        "adjusted energy (previously captured)": {},
                        "adjusted energy (competed)": {},
                        "adjusted energy (competed and captured)": {}},
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}}}
        cls.verbose = None
        cls.sample_measure_in = ecm_prep.Measure(
            handyvars, **sample_measure_in)
        cls.sample_convertdata_ok_in = {
            "building type conversions": {
                "original type": "EnergyPlus reference buildings",
                "revised type": "Annual Energy Outlook (AEO) buildings",
                "conversion data": {
                    "description": "sample",
                    "value": {
                        "residential": {
                            "single family home": {
                                "Single-Family": 1},
                            "mobile home": {
                                "Single-Family": 1},
                            "multi family home": {
                                "Multifamily": 1}},
                        "commercial": {
                            "assembly": {
                                "Hospital": 1},
                            "education": {
                                "PrimarySchool": 0.26,
                                "SecondarySchool": 0.74},
                            "food sales": {
                                "Supermarket": 1},
                            "food service": {
                                "QuickServiceRestaurant": 0.31,
                                "FullServiceRestaurant": 0.69},
                            "health care": None,
                            "lodging": {
                                "SmallHotel": 0.26,
                                "LargeHotel": 0.74},
                            "large office": {
                                "LargeOffice": 0.9,
                                "MediumOffice": 0.1},
                            "small office": {
                                "SmallOffice": 0.12,
                                "OutpatientHealthcare": 0.88},
                            "mercantile/service": {
                                "RetailStandalone": 0.53,
                                "RetailStripmall": 0.47},
                            "warehouse": {
                                "Warehouse": 1},
                            "other": None}},
                    "source": {
                        "residential": "sample",
                        "commercial": "sample"},
                    "notes": {
                        "residential": "sample",
                        "commercial": "sample"}}},
            "cost unit conversions": {
                "whole building": {
                    "wireless sensor network": {
                        "original units": "$/node",
                        "revised units": "$/ft^2 floor",
                        "conversion factor": {
                            "description": "sample",
                            "value": {
                                "residential": {
                                    "single family home": 0.0021,
                                    "mobile home": 0.0021,
                                    "multi family home": 0.0041},
                                "commercial": 0.002},
                            "units": "nodes/ft^2 floor",
                            "source": {
                                "residential": "sample",
                                "commercial": "sample"},
                            "notes": "sample"}},
                    "occupant-centered sensing and controls": {
                        "original units": "$/occupant",
                        "revised units": "$/ft^2 floor",
                        "conversion factor": {
                            "description": "sample",
                            "value": {
                                "residential": {
                                    "single family home": {
                                        "Single-Family": 0.001075},
                                    "mobile home": {
                                        "Single-Family": 0.001075},
                                    "multi family home": {
                                        "Multifamily": 0.00215}},
                                "commercial": {
                                    "assembly": {
                                        "Hospital": 0.005},
                                    "education": {
                                        "PrimarySchool": 0.02,
                                        "SecondarySchool": 0.02},
                                    "food sales": {
                                        "Supermarket": 0.008},
                                    "food service": {
                                        "QuickServiceRestaurant": 0.07,
                                        "FullServiceRestaurant": 0.07},
                                    "health care": 0.005,
                                    "lodging": {
                                        "SmallHotel": 0.005,
                                        "LargeHotel": 0.005},
                                    "large office": {
                                        "LargeOffice": 0.005,
                                        "MediumOffice": 0.005},
                                    "small office": {
                                        "SmallOffice": 0.005,
                                        "OutpatientHealthcare": 0.02},
                                    "mercantile/service": {
                                        "RetailStandalone": 0.01,
                                        "RetailStripmall": 0.01},
                                    "warehouse": {
                                        "Warehouse": 0.0001},
                                    "other": 0.005}},
                            "units": "occupants/ft^2 floor",
                            "source": {
                                "residential": "sample",
                                "commercial": "sample"},
                            "notes": ""}}},
                "heating and cooling": {
                    "supply": {
                        "heating equipment": {
                            "original units": "$/kBtu/h heating",
                            "revised units": "$/ft^2 floor",
                            "conversion factor": {
                                "description": "sample",
                                "value": 0.020,
                                "units": "kBtu/h heating/ft^2 floor",
                                "source": "Rule of thumb",
                                "notes": "sample"}},
                        "cooling equipment": {
                            "original units": "$/kBtu/h cooling",
                            "revised units": "$/ft^2 floor",
                            "conversion factor": {
                                "description": "sample",
                                "value": 0.036,
                                "units": "kBtu/h cooling/ft^2 floor",
                                "source": "Rule of thumb",
                                "notes": "sample"}}},
                    "demand": {
                        "windows": {
                            "original units": "$/ft^2 glazing",
                            "revised units": "$/ft^2 wall",
                            "conversion factor": {
                                "description": "Window to wall ratio",
                                "value": {
                                    "residential": {
                                        "single family home": {
                                            "Single-Family": 0.15},
                                        "mobile home": {
                                            "Single-Family": 0.15},
                                        "multi family home": {
                                            "Multifamily": 0.10}},
                                    "commercial": {
                                        "assembly": {
                                            "Hospital": 0.15},
                                        "education": {
                                            "PrimarySchool": 0.35,
                                            "SecondarySchool": 0.33},
                                        "food sales": {
                                            "Supermarket": 0.11},
                                        "food service": {
                                            "QuickServiceRestaurant": 0.14,
                                            "FullServiceRestaurant": 0.17},
                                        "health care": 0.2,
                                        "lodging": {
                                            "SmallHotel": 0.11,
                                            "LargeHotel": 0.27},
                                        "large office": {
                                            "LargeOffice": 0.38,
                                            "MediumOffice": 0.33},
                                        "small office": {
                                            "SmallOffice": 0.21,
                                            "OutpatientHealthcare": 0.19},
                                        "mercantile/service": {
                                            "RetailStandalone": 0.07,
                                            "RetailStripmall": 0.11},
                                        "warehouse": {
                                            "Warehouse": 0.006},
                                        "other": 0.2}},
                                "units": None,
                                "source": {
                                    "residential": "sample",
                                    "commercial": "sample"},
                                "notes": "sample"}},
                        "walls": {
                            "original units": "$/ft^2 wall",
                            "revised units": "$/ft^2 floor",
                            "conversion factor": {
                                "description": "Wall to floor ratio",
                                "value": {
                                    "residential": {
                                        "single family home": {
                                            "Single-Family": 1},
                                        "mobile home": {
                                            "Single-Family": 1},
                                        "multi family home": {
                                            "Multifamily": 1}},
                                    "commercial": {
                                        "assembly": {
                                            "Hospital": 0.26},
                                        "education": {
                                            "PrimarySchool": 0.20,
                                            "SecondarySchool": 0.16},
                                        "food sales": {
                                            "Supermarket": 0.38},
                                        "food service": {
                                            "QuickServiceRestaurant": 0.80,
                                            "FullServiceRestaurant": 0.54},
                                        "health care": 0.4,
                                        "lodging": {
                                            "SmallHotel": 0.40,
                                            "LargeHotel": 0.38},
                                        "large office": {
                                            "LargeOffice": 0.26,
                                            "MediumOffice": 0.40},
                                        "small office": {
                                            "SmallOffice": 0.55,
                                            "OutpatientHealthcare": 0.35},
                                        "mercantile/service": {
                                            "RetailStandalone": 0.51,
                                            "RetailStripmall": 0.57},
                                        "warehouse": {
                                            "Warehouse": 0.53},
                                        "other": 0.4}},
                                "units": None,
                                "source": {
                                    "residential": "sample",
                                    "commercial": "sample"},
                                "notes": "sample"}},
                        "footprint": {
                            "original units": "$/ft^2 footprint",
                            "revised units": "$/ft^2 floor",
                            "conversion factor": {
                                "description": "sample",
                                "value": {
                                    "residential": {
                                        "single family home": {
                                            "Single-Family": 0.5},
                                        "mobile home": {
                                            "Single-Family": 0.5},
                                        "multi family home": {
                                            "Multifamily": 0.33}},
                                    "commercial": {
                                        "assembly": {
                                            "Hospital": 0.20},
                                        "education": {
                                            "PrimarySchool": 1,
                                            "SecondarySchool": 0.5},
                                        "food sales": {"Supermarket": 1},
                                        "food service": {
                                            "QuickServiceRestaurant": 1,
                                            "FullServiceRestaurant": 1},
                                        "health care": 0.2,
                                        "lodging": {
                                            "SmallHotel": 0.25,
                                            "LargeHotel": 0.17},
                                        "large office": {
                                            "LargeOffice": 0.083,
                                            "MediumOffice": 0.33},
                                        "small office": {
                                            "SmallOffice": 1,
                                            "OutpatientHealthcare": 0.33},
                                        "mercantile/service": {
                                            "RetailStandalone": 1,
                                            "RetailStripmall": 1},
                                        "warehouse": {
                                            "Warehouse": 1},
                                        "other": 1}},
                                "units": None,
                                "source": {
                                    "residential": "sample",
                                    "commercial": "sample"},
                                "notes": "sample"}},
                        "roof": {
                            "original units": "$/ft^2 roof",
                            "revised units": "$/ft^2 footprint",
                            "conversion factor": {
                                "description": "sample",
                                "value": {
                                    "residential": 1.05,
                                    "commercial": 1},
                                "units": None,
                                "source": "Rule of thumb",
                                "notes": "sample"}}}},
                "ventilation": {
                    "original units": "$/1000 CFM",
                    "revised units": "$/ft^2 floor",
                    "conversion factor": {
                        "description": "sample",
                        "value": 0.001,
                        "units": "1000 CFM/ft^2 floor",
                        "source": "Rule of thumb",
                        "notes": "sample"}},
                "lighting": {
                    "original units": "$/1000 lm",
                    "revised units": "$/ft^2 floor",
                    "conversion factor": {
                        "description": "sample",
                        "value": 0.049,
                        "units": "1000 lm/ft^2 floor",
                        "source": "sample",
                        "notes": "sample"}},
                "water heating": {
                    "original units": "$/kBtu/h water heating",
                    "revised units": "$/ft^2 floor",
                    "conversion factor": {
                        "description": "sample",
                        "value": 0.012,
                        "units": "kBtu/h water heating/ft^2 floor",
                        "source": "sample",
                        "notes": "sample"}},
                "refrigeration": {
                    "original units": "$/kBtu/h refrigeration",
                    "revised units": "$/ft^2 floor",
                    "conversion factor": {
                        "description": "sample",
                        "value": 0.02,
                        "units": "kBtu/h refrigeration/ft^2 floor",
                        "source": "sample",
                        "notes": "sample"}},
                "cooking": {},
                "MELs": {}
            }
        }
        cls.sample_bldgsect_ok_in = [
            "residential", "commercial", "commercial", "commercial",
            "commercial", "commercial", "commercial", "commercial",
            "residential", "residential", "commercial", "residential",
            "residential"]
        cls.sample_mskeys_ok_in = [
            ('primary', 'marine', 'single family home', 'electricity',
             'cooling', 'demand', 'windows conduction', 'existing'),
            ('primary', 'marine', 'assembly', 'electricity', 'heating',
             'supply', 'rooftop_ASHP-heat', 'new'),
            ('primary', 'marine', 'food sales', 'electricity', 'cooling',
             'demand', 'ground', 'new'),
            ('primary', 'marine', 'education', 'electricity', 'cooling',
             'demand', 'roof', 'existing'),
            ('primary', 'marine', 'lodging', 'electricity', 'cooling',
             'demand', 'wall', 'new'),
            ('primary', 'marine', 'food service', 'electricity', 'ventilation',
             'CAV_Vent', 'existing'),
            ('primary', 'marine', 'small office', 'electricity', 'cooling',
             'reciprocating_chiller', 'existing'),
            ('primary', 'mixed humid', 'health care', 'electricity', 'cooling',
             'demand', 'roof', 'existing'),
            ('primary', 'mixed humid', 'single family home', 'electricity',
             'cooling', 'supply', 'ASHP'),
            ('primary', 'mixed humid', 'single family home', 'electricity',
             'lighting', 'linear fluorescent (LED)'),
            ('primary', 'marine', 'food service', 'electricity', 'ventilation',
             'CAV_Vent', 'existing'),
            ('primary', 'mixed humid', 'multi family home', 'electricity',
             'lighting', 'general service (CFL)'),
            ('primary', 'mixed humid', 'multi family home', 'electricity',
             'lighting', 'general service (CFL)')]
        cls.sample_mskeys_fail_in = [
            ('primary', 'marine', 'single family home', 'electricity',
             'cooling', 'demand', 'windows conduction', 'existing'),
            ('primary', 'marine', 'assembly', 'electricity', 'PCs',
             None, 'new'),
            ('primary', 'marine', 'single family home', 'electricity', 'PCs',
             None, 'new')]
        cls.cost_meas_ok_in = 10
        cls.cost_meas_units_ok_in_yronly = '2008$/ft^2 floor'
        cls.cost_meas_units_ok_in_all = [
            '$/ft^2 glazing', '2013$/kBtu/h heating', '2010$/ft^2 footprint',
            '2016$/ft^2 roof', '2013$/ft^2 wall', '2012$/1000 CFM',
            '2013$/occupant', '2013$/ft^2 roof', '2013$/node',
            '2013$/ft^2 floor', '2013$/node', '2013$/node',
            '2013$/occupant']
        cls.cost_meas_units_fail_in = [
            '$/ft^2 facade', '$/kWh', '$/ft^2 floor']
        cls.cost_base_units_fail_in = [
            '2013$/ft^2 floor', '2013$/ft^2 floor', '2013$/unit']
        cls.cost_base_units_ok_in = numpy.repeat('2013$/ft^2 floor', 13)
        cls.ok_out_costs_yronly = 11.11
        cls.ok_out_costs_all = [
            1.47, 0.2, 10.65, 6.18, 3.85, 0.01015, 0.182,
            2, 0.021, 10, 0.02, 0.041, 0.0215]

    def test_convertcost_ok_yronly(self):
        """Test 'convert_costs' function for year only conversion."""
        func_output = self.sample_measure_in.convert_costs(
            self.sample_convertdata_ok_in, self.sample_bldgsect_ok_in[0],
            self.sample_mskeys_ok_in[0], self.cost_meas_ok_in,
            self.cost_meas_units_ok_in_yronly,
            self.cost_base_units_ok_in[0], self.verbose)
        numpy.testing.assert_almost_equal(
            func_output[0], self.ok_out_costs_yronly, decimal=2)
        self.assertEqual(func_output[1], self.cost_base_units_ok_in[0])

    def test_convertcost_ok_all(self):
        """Test 'convert_costs' function for year/units conversion."""
        for k in range(0, len(self.sample_mskeys_ok_in)):
            func_output = self.sample_measure_in.convert_costs(
                self.sample_convertdata_ok_in, self.sample_bldgsect_ok_in[k],
                self.sample_mskeys_ok_in[k], self.cost_meas_ok_in,
                self.cost_meas_units_ok_in_all[k],
                self.cost_base_units_ok_in[k], self.verbose)
            numpy.testing.assert_almost_equal(
                func_output[0], self.ok_out_costs_all[k], decimal=2)
            self.assertEqual(
                func_output[1], self.cost_base_units_ok_in[k])

    def test_convertcost_fail(self):
        """Test 'convert_costs' function given invalid inputs."""
        for k in range(0, len(self.sample_mskeys_fail_in)):
            with self.assertRaises(KeyError):
                self.sample_measure_in.convert_costs(
                    self.sample_convertdata_ok_in,
                    self.sample_bldgsect_ok_in[k],
                    self.sample_mskeys_fail_in[k], self.cost_meas_ok_in,
                    self.cost_meas_units_fail_in[k],
                    self.cost_base_units_fail_in[k], self.verbose)


class UpdateMeasuresTest(unittest.TestCase, CommonMethods):
    """Test 'prepare_measures' function.

    Ensure that function properly instantiates Measure objects and finalizes
    attributes for these objects.

    Attributes:
        handyvars (object): Global variables to use across measures.
        verbose (NoneType): Determines whether to print all user messages.
        cbecs_sf_byvint (dict): Commercial square footage by vintage data.
        sample_mseg_in (dict): Sample baseline microsegment stock/energy.
        sample_cpl_in (dict): Sample baseline technology cost, performance,
            and lifetime.
        measures_ok_in (list): List of measures with valid user-defined
            'status' attributes.
        measures_warn_in (list): List of measures that includes one measure
            with invalid 'status' attribute (the measure's 'markets' attribute
            has not been finalized but user has not flagged it for an update).
        convert_data (dict): Data used to convert expected
            user-defined measure cost units to cost units required by Scout
            analysis engine.
        ok_out (list): List of measure master microsegment dicts that
            should be generated by 'prepare_measures' given sample input
            measure information to update and an assumed technical potential
            adoption scenario.
        ok_warnmeas_out (list): Warnings that should be yielded when running
            'measures_warn_in' through the function.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        cls.base_dir = os.getcwd()
        cls.handyvars = ecm_prep.UsefulVars(cls.base_dir,
                                            ecm_prep.UsefulInputFiles())
        # Hard code aeo_years to fit test years
        cls.handyvars.aeo_years = ["2009", "2010"]
        cls.cbecs_sf_byvint = {
            '2004 to 2007': 6524.0, '1960 to 1969': 10362.0,
            '1946 to 1959': 7381.0, '1970 to 1979': 10846.0,
            '1990 to 1999': 13803.0, '2000 to 2003': 7215.0,
            'Before 1920': 3980.0, '2008 to 2012': 5726.0,
            '1920 to 1945': 6020.0, '1980 to 1989': 15185.0}
        # Hard code carbon intensity, site-source conversion, and cost data for
        # tests such that these data are not dependent on an input file that
        # may change in the future
        cls.handyvars.ss_conv = {
            "electricity": {"2009": 3.19, "2010": 3.20},
            "natural gas": {"2009": 1.01, "2010": 1.01},
            "distillate": {"2009": 1.01, "2010": 1.01},
            "other fuel": {"2009": 1.01, "2010": 1.01}}
        cls.handyvars.carb_int = {
            "residential": {
                "electricity": {"2009": 56.84702689, "2010": 56.16823191},
                "natural gas": {"2009": 56.51576602, "2010": 54.91762852},
                "distillate": {"2009": 49.5454521, "2010": 52.59751597},
                "other fuel": {"2009": 49.5454521, "2010": 52.59751597}},
            "commercial": {
                "electricity": {"2009": 56.84702689, "2010": 56.16823191},
                "natural gas": {"2009": 56.51576602, "2010": 54.91762852},
                "distillate": {"2009": 49.5454521, "2010": 52.59751597},
                "other fuel": {"2009": 49.5454521, "2010": 52.59751597}}}
        cls.handyvars.ecosts = {
            "residential": {
                "electricity": {"2009": 10.14, "2010": 9.67},
                "natural gas": {"2009": 11.28, "2010": 10.78},
                "distillate": {"2009": 21.23, "2010": 20.59},
                "other fuel": {"2009": 21.23, "2010": 20.59}},
            "commercial": {
                "electricity": {"2009": 9.08, "2010": 8.55},
                "natural gas": {"2009": 8.96, "2010": 8.59},
                "distillate": {"2009": 14.81, "2010": 14.87},
                "other fuel": {"2009": 14.81, "2010": 14.87}}}
        cls.handyvars.ccosts = {"2009": 33, "2010": 33}
        cls.verbose = None
        cls.sample_mseg_in = {
            "AIA_CZ1": {
                "single family home": {
                    "total square footage": {"2009": 100, "2010": 200},
                    "total homes": {"2009": 1000, "2010": 1000},
                    "new homes": {"2009": 100, "2010": 50},
                    "natural gas": {
                        "water heating": {
                            "stock": {"2009": 15, "2010": 15},
                            "energy": {"2009": 15, "2010": 15}}}}}}
        cls.sample_cpl_in = {
            "AIA_CZ1": {
                "single family home": {
                    "natural gas": {
                        "water heating": {
                            "performance": {
                                "typical": {"2009": 18, "2010": 18},
                                "best": {"2009": 18, "2010": 18},
                                "units": "EF",
                                "source":
                                "EIA AEO"},
                            "installed cost": {
                                "typical": {"2009": 18, "2010": 18},
                                "best": {"2009": 18, "2010": 18},
                                "units": "2014$/unit",
                                "source": "EIA AEO"},
                            "lifetime": {
                                "average": {"2009": 180, "2010": 180},
                                "range": {"2009": 18, "2010": 18},
                                "units": "years",
                                "source": "EIA AEO"},
                            "consumer choice": {
                                "competed market share": {
                                    "source": "EIA AEO",
                                    "model type": "logistic regression",
                                    "parameters": {
                                        "b1": {"2009": "NA", "2010": "NA"},
                                        "b2": {"2009": "NA",
                                               "2010": "NA"}}},
                                "competed market": {
                                    "source": "COBAM",
                                    "model type": "bass diffusion",
                                    "parameters": {
                                        "p": "NA",
                                        "q": "NA"}}}}}}}}
        cls.convert_data = {}  # Blank for now
        cls.measures_ok_in = [{
            "name": "sample measure to prepare",
            "markets": None,
            "installed_cost": 25,
            "cost_units": "2014$/unit",
            "energy_efficiency": {
                "new": 25, "existing": 25},
            "energy_efficiency_units": "EF",
            "market_entry_year": None,
            "market_exit_year": None,
            "product_lifetime": 1,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "bldg_type": "single family home",
            "climate_zone": "AIA_CZ1",
            "fuel_type": "natural gas",
            "fuel_switch_to": None,
            "end_use": "water heating",
            "technology": None}]
        cls.ok_out = [{
            "stock": {
                "total": {
                    "all": {"2009": 15, "2010": 15},
                    "measure": {"2009": 15, "2010": 15}},
                "competed": {
                    "all": {"2009": 15, "2010": 15},
                    "measure": {"2009": 15, "2010": 15}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 15.15, "2010": 15.15},
                    "efficient": {"2009": 10.908, "2010": 10.908}},
                "competed": {
                    "baseline": {"2009": 15.15, "2010": 15.15},
                    "efficient": {"2009": 10.908, "2010": 10.908}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 856.2139, "2010": 832.0021},
                    "efficient": {"2009": 616.474, "2010": 599.0415}},
                "competed": {
                    "baseline": {"2009": 856.2139, "2010": 832.0021},
                    "efficient": {"2009": 616.474, "2010": 599.0415}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 270, "2010": 270},
                        "efficient": {"2009": 375, "2010": 375}},
                    "competed": {
                        "baseline": {"2009": 270, "2010": 270},
                        "efficient": {"2009": 375, "2010": 375}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 170.892, "2010": 163.317},
                        "efficient": {"2009": 123.0422, "2010": 117.5882}},
                    "competed": {
                        "baseline": {"2009": 170.892, "2010": 163.317},
                        "efficient": {"2009": 123.0422, "2010": 117.5882}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 28255.06, "2010": 27456.07},
                        "efficient": {"2009": 20343.64, "2010": 19768.37}},
                    "competed": {
                        "baseline": {"2009": 28255.06, "2010": 27456.07},
                        "efficient": {"2009": 20343.64, "2010": 19768.37}}}},
            "lifetime": {"baseline": {"2009": 180, "2010": 180},
                         "measure": 1}}]

    def test_fillmeas_ok(self):
        """Test 'prepare_measures' function given valid measure inputs.

        Note:
            Ensure that function properly identifies which input measures
            require updating and that the updates are performed correctly.
        """
        measures_out = ecm_prep.prepare_measures(
            self.measures_ok_in, self.convert_data, self.sample_mseg_in,
            self.sample_cpl_in, self.handyvars, self.cbecs_sf_byvint,
            self.base_dir, self.verbose)
        for oc in range(0, len(self.ok_out)):
            self.dict_check(
                measures_out[oc].markets[
                    "Technical potential"]["master_mseg"], self.ok_out[oc])


class MergeMeasuresandApplyBenefitsTest(unittest.TestCase, CommonMethods):
    """Test 'merge_measures' and 'apply_pkg_benefits' functions.

    Ensure that the 'merge_measures' function correctly assembles a series of
    attributes for individual measures into attributes for a packaged measure,
    and that the 'apply_pkg_benefits' function correctly applies additional
    energy savings and installed cost benefits for a package measure.

    Attributes:
        sample_measures_in (list): List of valid sample measure attributes
            to package.
        sample_package_name (string): Sample packaged measure name.
        sample_package_in_test1 (object): Sample packaged measure object to
            update in the test of the 'merge_measures' function.
        sample_package_in_test2 (object): Sample packaged measure object to
            initialize for the test of the 'apply_pkg_benefits' function.
        genattr_ok_out_test1 (list): General attributes that should be yielded
            for the packaged measure in the 'merge_measures' test, given valid
            sample measures to merge.
        markets_ok_out_test1 (dict): Packaged measure stock, energy, carbon,
            and cost data that should be yielded in the 'merge_measures' test,
            given valid sample measures to merge.
        mseg_ok_in_test2 (dict): Energy, carbon, and cost data to apply
            additional energy savings and cost reduction benefits to in the
            'apply_pkg_benefits' test.
        mseg_ok_out_test2 (dict): Updated energy, carbon, and cost data
            that should be yielded in 'apply_pkg_benefits' test, given valid
            input data to apply packaging benefits to.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        # Define additional energy savings and cost reduction benefits to
        # apply to the energy, carbon, and cost data for a package in the
        # 'merge_measures' test
        benefits_test1 = {
            "energy savings increase": 0,
            "cost reduction": 0}
        # Define additional energy savings and cost reduction benefits to
        # apply to the energy, carbon, and cost data for a package in the
        # 'apply_pkg_benefits' test
        benefits_test2 = {
            "energy savings increase": 0.3,
            "cost reduction": 0.2}
        # Useful global variables for the sample package measure objects
        handyvars = ecm_prep.UsefulVars(base_dir,
                                        ecm_prep.UsefulInputFiles())
        # Hard code aeo_years to fit test years
        handyvars.aeo_years = ["2009", "2010"]
        # Define a series of sample measures to package
        sample_measures_in = [{
            "name": "sample measure pkg 1",
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ2"],
            "bldg_type": ["single family home"],
            "fuel_type": ["natural gas"],
            "fuel_switch_to": None,
            "end_use": {"primary": ["water heating"],
                        "secondary": None},
            "technology": [None],
            "technology_type": {
                "primary": "supply", "secondary": None},
            "markets": {
                "Technical potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 40, "2010": 40},
                                "measure": {"2009": 24, "2010": 24}},
                            "competed": {
                                "all": {"2009": 20, "2010": 20},
                                "measure": {"2009": 4, "2010": 4}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 80, "2010": 80},
                                "efficient": {"2009": 48, "2010": 48}},
                            "competed": {
                                "baseline": {"2009": 40, "2010": 40},
                                "efficient": {"2009": 8, "2010": 8}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 120, "2010": 120},
                                "efficient": {"2009": 72, "2010": 72}},
                            "competed": {
                                "baseline": {"2009": 60, "2010": 60},
                                "efficient": {"2009": 12, "2010": 12}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {"2009": 40, "2010": 40},
                                    "efficient": {"2009": 72, "2010": 72}},
                                "competed": {
                                    "baseline": {"2009": 40, "2010": 40},
                                    "efficient": {"2009": 72, "2010": 72}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 80, "2010": 80},
                                    "efficient": {"2009": 48, "2010": 48}},
                                "competed": {
                                    "baseline": {"2009": 40, "2010": 40},
                                    "efficient": {"2009": 8, "2010": 8}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 120, "2010": 120},
                                    "efficient": {"2009": 72, "2010": 72}},
                                "competed": {
                                    "baseline": {"2009": 60, "2010": 60},
                                    "efficient": {"2009": 12, "2010": 12}}}},
                        "lifetime": {
                            "baseline": {"2009": 5, "2010": 5},
                            "measure": 10}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0.5, "2010": 0.5},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0, "2010": 0},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0.5, "2010": 0.5},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0, "2010": 0},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}}}},
                "Max adoption potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 40, "2010": 40},
                                "measure": {"2009": 24, "2010": 24}},
                            "competed": {
                                "all": {"2009": 20, "2010": 20},
                                "measure": {"2009": 4, "2010": 4}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 80, "2010": 80},
                                "efficient": {"2009": 48, "2010": 48}},
                            "competed": {
                                "baseline": {"2009": 40, "2010": 40},
                                "efficient": {"2009": 8, "2010": 8}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 120, "2010": 120},
                                "efficient": {"2009": 72, "2010": 72}},
                            "competed": {
                                "baseline": {"2009": 60, "2010": 60},
                                "efficient": {"2009": 12, "2010": 12}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {"2009": 40, "2010": 40},
                                    "efficient": {"2009": 72, "2010": 72}},
                                "competed": {
                                    "baseline": {"2009": 40, "2010": 40},
                                    "efficient": {"2009": 72, "2010": 72}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 80, "2010": 80},
                                    "efficient": {"2009": 48, "2010": 48}},
                                "competed": {
                                    "baseline": {"2009": 40, "2010": 40},
                                    "efficient": {"2009": 8, "2010": 8}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 120, "2010": 120},
                                    "efficient": {"2009": 72, "2010": 72}},
                                "competed": {
                                    "baseline": {"2009": 60, "2010": 60},
                                    "efficient": {"2009": 12, "2010": 12}}}},
                        "lifetime": {
                            "baseline": {"2009": 5, "2010": 5},
                            "measure": 10}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 10, "2010": 10},
                                        "measure": {"2009": 6, "2010": 6}},
                                    "competed": {
                                        "all": {"2009": 5, "2010": 5},
                                        "measure": {"2009": 1, "2010": 1}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 18, "2010": 18}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 20, "2010": 20},
                                            "efficient": {
                                                "2009": 12, "2010": 12}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 10, "2010": 10},
                                            "efficient": {
                                                "2009": 2, "2010": 2}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 30, "2010": 30},
                                            "efficient": {
                                                "2009": 18, "2010": 18}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 15, "2010": 15},
                                            "efficient": {
                                                "2009": 3, "2010": 3}}}},
                                "lifetime": {
                                    "baseline": {"2009": 5, "2010": 5},
                                    "measure": 10},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, 'new')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}},
                            ("('primary', AIA_CZ2', 'single family home', "
                             "'natural gas', 'water heating', None, "
                             "'existing')"): {
                                "b1": {"2009": 0.5, "2010": 0.5},
                                "b2": {"2009": 0.5, "2010": 0.5}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0.5, "2010": 0.5},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0, "2010": 0},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0.5, "2010": 0.5},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {
                                    "2009": 0, "2010": 0},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}}}}},
            "out_break_norm": {
                "Technical potential": {"2009": 80, "2010": 80},
                "Max adoption potential": {"2009": 80, "2010": 80}}},
            {
            "name": "sample measure pkg 2",
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["existing"],
            "climate_zone": ["AIA_CZ1"],
            "bldg_type": ["single family home"],
            "fuel_type": ["electricity"],
            "fuel_switch_to": None,
            "end_use": {"primary": ["lighting"],
                        "secondary": None},
            "technology": [
                "reflector (incandescent)",
                "reflector (halogen)"],
            "technology_type": {
                "primary": "supply", "secondary": None},
            "markets": {
                "Technical potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 200, "2010": 200},
                                "measure": {"2009": 120, "2010": 120}},
                            "competed": {
                                "all": {"2009": 100, "2010": 100},
                                "measure": {"2009": 20, "2010": 20}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 400, "2010": 400},
                                "efficient": {"2009": 240, "2010": 240}},
                            "competed": {
                                "baseline": {"2009": 200, "2010": 200},
                                "efficient": {"2009": 40, "2010": 40}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 600, "2010": 600},
                                "efficient": {"2009": 360, "2010": 360}},
                            "competed": {
                                "baseline": {"2009": 300, "2010": 300},
                                "efficient": {"2009": 60, "2010": 60}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 400, "2010": 400},
                                    "efficient": {"2009": 240, "2010": 240}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 40, "2010": 40}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 600, "2010": 600},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 300, "2010": 300},
                                    "efficient": {"2009": 60, "2010": 60}}}},
                        "lifetime": {
                            "baseline": {"2009": 1, "2010": 1},
                            "measure": 20}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (halogen)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 2, "2010": 2},
                                    "measure": 15},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (halogen)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {
                                    "2009": 1, "2010": 1},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}}}},
                "Max adoption potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 200, "2010": 200},
                                "measure": {"2009": 120, "2010": 120}},
                            "competed": {
                                "all": {"2009": 100, "2010": 100},
                                "measure": {"2009": 20, "2010": 20}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 400, "2010": 400},
                                "efficient": {"2009": 240, "2010": 240}},
                            "competed": {
                                "baseline": {"2009": 200, "2010": 200},
                                "efficient": {"2009": 40, "2010": 40}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 600, "2010": 600},
                                "efficient": {"2009": 360, "2010": 360}},
                            "competed": {
                                "baseline": {"2009": 300, "2010": 300},
                                "efficient": {"2009": 60, "2010": 60}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 400, "2010": 400},
                                    "efficient": {"2009": 240, "2010": 240}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 40, "2010": 40}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 600, "2010": 600},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 300, "2010": 300},
                                    "efficient": {"2009": 60, "2010": 60}}}},
                        "lifetime": {
                            "baseline": {"2009": 1, "2010": 1},
                            "measure": 20}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (halogen)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 2, "2010": 2},
                                    "measure": 15},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (halogen)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {
                                    "2009": 1, "2010": 1},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}}}}},
            "out_break_norm": {
                "Technical potential": {"2009": 400, "2010": 400},
                "Max adoption potential": {"2009": 400, "2010": 400}}},
            {
            "name": "sample measure pkg 3",
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "full service",
            "structure_type": ["new", "existing"],
            "climate_zone": ["AIA_CZ1", "AIA_CZ5"],
            "bldg_type": ["multi family home"],
            "fuel_type": ["electricity"],
            "fuel_switch_to": None,
            "end_use": {
                "primary": ["cooling", "lighting"],
                "secondary": None},
            "technology": [
                    "ASHP",
                    "reflector (incandescent)"],
            "technology_type": {
                "primary": "supply", "secondary": None},
            "markets": {
                "Technical potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 1100, "2010": 1100},
                                "measure": {"2009": 660, "2010": 660}},
                            "competed": {
                                "all": {"2009": 550, "2010": 550},
                                "measure": {"2009": 110, "2010": 110}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 2200, "2010": 2200},
                                "efficient": {"2009": 1320, "2010": 1320}},
                            "competed": {
                                "baseline": {"2009": 1100, "2010": 1100},
                                "efficient": {"2009": 220, "2010": 220}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 3300, "2010": 3300},
                                "efficient": {"2009": 1980, "2010": 1980}},
                            "competed": {
                                "baseline": {"2009": 1650, "2010": 1650},
                                "efficient": {"2009": 330, "2010": 330}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 400, "2010": 400},
                                    "efficient": {"2009": 240, "2010": 240}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 40, "2010": 40}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 600, "2010": 600},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 300, "2010": 300},
                                    "efficient": {"2009": 60, "2010": 60}}}},
                        "lifetime": {
                            "baseline": {"2009": 18, "2010": 18},
                            "measure": 18}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ5', 'single family home', "
                             "'electricity',"
                             "'cooling', 'supply', 'ASHP', 'new')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 1000, "2010": 1000},
                                        "measure": {"2009": 600, "2010": 600}},
                                    "competed": {
                                        "all": {"2009": 500, "2010": 500},
                                        "measure": {
                                            "2009": 100, "2010": 100}}},
                                "energy": {
                                    "total": {
                                        "baseline": {
                                            "2009": 2000, "2010": 2000},
                                        "efficient": {
                                            "2009": 1200, "2010": 1200}},
                                    "competed": {
                                        "baseline": {
                                            "2009": 1000, "2010": 1000},
                                        "efficient": {
                                            "2009": 200, "2010": 200}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {
                                            "2009": 3000, "2010": 3000},
                                        "efficient": {
                                            "2009": 1800, "2010": 1800}},
                                    "competed": {
                                        "baseline": {
                                            "2009": 1500, "2010": 1500},
                                        "efficient": {
                                            "2009": 300, "2010": 300}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 18, "2010": 18},
                                    "measure": 18},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ5', 'single family home', "
                             "'electricity',"
                             "'cooling', 'supply', 'ASHP', 'new')"): {
                                "b1": {"2009": 0.75, "2010": 0.75},
                                "b2": {"2009": 0.75, "2010": 0.75}},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (halogen)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {
                                    "2009": 0.5, "2010": 0.5},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {
                                    "2009": 0.5, "2010": 0.5},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}}}},
                "Max adoption potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 1100, "2010": 1100},
                                "measure": {"2009": 660, "2010": 660}},
                            "competed": {
                                "all": {"2009": 550, "2010": 550},
                                "measure": {"2009": 110, "2010": 110}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 2200, "2010": 2200},
                                "efficient": {"2009": 1320, "2010": 1320}},
                            "competed": {
                                "baseline": {"2009": 1100, "2010": 1100},
                                "efficient": {"2009": 220, "2010": 220}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 3300, "2010": 3300},
                                "efficient": {"2009": 1980, "2010": 1980}},
                            "competed": {
                                "baseline": {"2009": 1650, "2010": 1650},
                                "efficient": {"2009": 330, "2010": 330}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 360, "2010": 360}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 400, "2010": 400},
                                    "efficient": {"2009": 240, "2010": 240}},
                                "competed": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 40, "2010": 40}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 600, "2010": 600},
                                    "efficient": {"2009": 360, "2010": 360}},
                                "competed": {
                                    "baseline": {"2009": 300, "2010": 300},
                                    "efficient": {"2009": 60, "2010": 60}}}},
                        "lifetime": {
                            "baseline": {"2009": 18, "2010": 18},
                            "measure": 18}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1},
                            ("('primary', AIA_CZ5', 'single family home', "
                             "'electricity',"
                             "'cooling', 'supply', 'ASHP', 'new')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 1000, "2010": 1000},
                                        "measure": {"2009": 600, "2010": 600}},
                                    "competed": {
                                        "all": {"2009": 500, "2010": 500},
                                        "measure": {
                                            "2009": 100, "2010": 100}}},
                                "energy": {
                                    "total": {
                                        "baseline": {
                                            "2009": 2000, "2010": 2000},
                                        "efficient": {
                                            "2009": 1200, "2010": 1200}},
                                    "competed": {
                                        "baseline": {
                                            "2009": 1000, "2010": 1000},
                                        "efficient": {
                                            "2009": 200, "2010": 200}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {
                                            "2009": 3000, "2010": 3000},
                                        "efficient": {
                                            "2009": 1800, "2010": 1800}},
                                    "competed": {
                                        "baseline": {
                                            "2009": 1500, "2010": 1500},
                                        "efficient": {
                                            "2009": 300, "2010": 300}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 18, "2010": 18},
                                    "measure": 18},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ5', 'single family home', "
                             "'electricity',"
                             "'cooling', 'supply', 'ASHP', 'new')"): {
                                "b1": {"2009": 0.75, "2010": 0.75},
                                "b2": {"2009": 0.75, "2010": 0.75}},
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (halogen)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {
                                    "2009": 0.5, "2010": 0.5},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {
                                    "2009": 0.5, "2010": 0.5},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {},
                                'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {},
                                'Envelope': {}}}}}},
            "out_break_norm": {
                "Technical potential": {"2009": 2200, "2010": 2200},
                "Max adoption potential": {"2009": 2200, "2010": 2200}}},
            {
            "name": "sample measure pkg 4",
            "market_entry_year": None,
            "market_exit_year": None,
            "market_scaling_fractions": None,
            "market_scaling_fractions_source": None,
            "measure_type": "add-on",
            "structure_type": ["existing"],
            "climate_zone": ["AIA_CZ1"],
            "bldg_type": ["single family home"],
            "fuel_type": ["electricity"],
            "fuel_switch_to": None,
            "end_use": {"primary": ["lighting"],
                        "secondary": None},
            "technology": [
                "reflector (incandescent)"],
            "technology_type": {
                "primary": "supply", "secondary": None},
            "markets": {
                "Technical potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 100, "2010": 100},
                                "measure": {"2009": 60, "2010": 60}},
                            "competed": {
                                "all": {"2009": 50, "2010": 50},
                                "measure": {"2009": 10, "2010": 10}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 200, "2010": 200},
                                "efficient": {
                                    "2009": 120, "2010": 120}},
                            "competed": {
                                "baseline": {"2009": 100, "2010": 100},
                                "efficient": {
                                    "2009": 20, "2010": 20}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 300, "2010": 300},
                                "efficient": {
                                    "2009": 180, "2010": 180}},
                            "competed": {
                                "baseline": {"2009": 150, "2010": 150},
                                "efficient": {
                                    "2009": 30, "2010": 30}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {
                                        "2009": 100, "2010": 100},
                                    "efficient": {
                                        "2009": 180, "2010": 180}},
                                "competed": {
                                    "baseline": {
                                        "2009": 100, "2010": 100},
                                    "efficient": {
                                        "2009": 180, "2010": 180}}},
                            "energy": {
                                "total": {
                                    "baseline": {
                                        "2009": 200, "2010": 200},
                                    "efficient": {
                                        "2009": 120, "2010": 120}},
                                "competed": {
                                    "baseline": {
                                        "2009": 100, "2010": 100},
                                    "efficient": {
                                        "2009": 20, "2010": 20}}},
                            "carbon": {
                                "total": {
                                    "baseline": {
                                        "2009": 300, "2010": 300},
                                    "efficient": {
                                        "2009": 180, "2010": 180}},
                                "competed": {
                                    "baseline": {
                                        "2009": 150, "2010": 150},
                                    "efficient": {
                                        "2009": 30, "2010": 30}}}},
                        "lifetime": {
                            "baseline": {"2009": 1, "2010": 1},
                            "measure": 20}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}
                                },
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {
                                    "2009": 1, "2010": 1},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}}}},
                "Max adoption potential": {
                    "master_mseg": {
                        "stock": {
                            "total": {
                                "all": {"2009": 100, "2010": 100},
                                "measure": {"2009": 60, "2010": 60}},
                            "competed": {
                                "all": {"2009": 50, "2010": 50},
                                "measure": {"2009": 10, "2010": 10}}},
                        "energy": {
                            "total": {
                                "baseline": {"2009": 200, "2010": 200},
                                "efficient": {
                                    "2009": 120, "2010": 120}},
                            "competed": {
                                "baseline": {"2009": 100, "2010": 100},
                                "efficient": {
                                    "2009": 20, "2010": 20}}},
                        "carbon": {
                            "total": {
                                "baseline": {"2009": 300, "2010": 300},
                                "efficient": {
                                    "2009": 180, "2010": 180}},
                            "competed": {
                                "baseline": {"2009": 150, "2010": 150},
                                "efficient": {
                                    "2009": 30, "2010": 30}}},
                        "cost": {
                            "stock": {
                                "total": {
                                    "baseline": {
                                        "2009": 100, "2010": 100},
                                    "efficient": {
                                        "2009": 180, "2010": 180}},
                                "competed": {
                                    "baseline": {
                                        "2009": 100, "2010": 100},
                                    "efficient": {
                                        "2009": 180, "2010": 180}}},
                            "energy": {
                                "total": {
                                    "baseline": {
                                        "2009": 200, "2010": 200},
                                    "efficient": {
                                        "2009": 120, "2010": 120}},
                                "competed": {
                                    "baseline": {
                                        "2009": 100, "2010": 100},
                                    "efficient": {
                                        "2009": 20, "2010": 20}}},
                            "carbon": {
                                "total": {
                                    "baseline": {
                                        "2009": 300, "2010": 300},
                                    "efficient": {
                                        "2009": 180, "2010": 180}},
                                "competed": {
                                    "baseline": {
                                        "2009": 150, "2010": 150},
                                    "efficient": {
                                        "2009": 30, "2010": 30}}}},
                        "lifetime": {
                            "baseline": {"2009": 1, "2010": 1},
                            "measure": 20}},
                    "mseg_adjust": {
                        "contributing mseg keys and values": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1}},
                        "competed choice parameters": {
                            ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "b1": {"2009": 0.25, "2010": 0.25},
                                "b2": {"2009": 0.25, "2010": 0.25}}},
                        "secondary mseg adjustments": {
                            "sub-market": {
                                "original energy (total)": {},
                                "adjusted energy (sub-market)": {}},
                            "stock-and-flow": {
                                "original energy (total)": {},
                                "adjusted energy (previously captured)": {},
                                "adjusted energy (competed)": {},
                                "adjusted energy (competed and captured)": {}},
                            "market share": {
                                "original energy (total captured)": {},
                                "original energy (competed and captured)": {},
                                "adjusted energy (total captured)": {},
                                "adjusted energy (competed and captured)": {}}}},
                    "mseg_out_break": {
                        'AIA CZ1': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {
                                    "2009": 1, "2010": 1},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ2': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ3': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ4': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}},
                        'AIA CZ5': {
                            'Residential (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Residential (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (New)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}},
                            'Commercial (Existing)': {
                                'Cooling (Equip.)': {}, 'Ventilation': {},
                                'Lighting': {},
                                'Refrigeration': {}, 'Other': {},
                                'Water Heating': {},
                                'Computers and Electronics': {},
                                'Heating (Equip.)': {}, 'Envelope': {}}}}}},
            "out_break_norm": {
                "Technical potential": {"2009": 200, "2010": 200},
                "Max adoption potential": {"2009": 200, "2010": 200}}}]
        cls.sample_measures_in = [ecm_prep.Measure(
            handyvars, **x) for x in sample_measures_in]
        # Reset sample measure technology types (initialized as string)
        for ind, m in enumerate(cls.sample_measures_in):
            m.technology_type = sample_measures_in[ind]["technology_type"]
        # Reset sample measure markets (initialized to None)
        for ind, m in enumerate(cls.sample_measures_in):
            m.markets = sample_measures_in[ind]["markets"]
        # Reset total absolute energy use figure used to normalize sample
        # measure energy savings summed by climate, building, and end use
        for ind, m in enumerate(cls.sample_measures_in):
            m.out_break_norm = sample_measures_in[ind]["out_break_norm"]
        cls.sample_package_name = "Package - CAC + CFLs + NGWH"
        cls.sample_package_in_test1 = ecm_prep.MeasurePackage(
            cls.sample_measures_in, cls.sample_package_name,
            benefits_test1, handyvars)
        cls.sample_package_in_test2 = ecm_prep.MeasurePackage(
            cls.sample_measures_in, cls.sample_package_name,
            benefits_test2, handyvars)
        cls.genattr_ok_out_test1 = [
            'Package - CAC + CFLs + NGWH',
            ['AIA_CZ1', 'AIA_CZ2', 'AIA_CZ5'],
            ['single family home', 'multi family home'],
            ['new', 'existing'],
            ['electricity', 'natural gas'],
            ['water heating', 'lighting', 'cooling']]
        cls.markets_ok_out_test1 = {
            "Technical potential": {
                "master_mseg": {
                    'stock': {
                        'total': {
                            'all': {'2009': 1240, '2010': 1240},
                            'measure': {'2009': 744, '2010': 744}},
                        'competed': {
                            'all': {'2009': 620, '2010': 620},
                            'measure': {'2009': 124, '2010': 124}}},
                    'energy': {
                        'total': {
                            'baseline': {'2009': 2480, '2010': 2480},
                            'efficient': {'2009': 1488, '2010': 1488}},
                        'competed': {
                            'baseline': {'2009': 1240, '2010': 1240},
                            'efficient': {'2009': 248, '2010': 248}}},
                    'carbon': {
                        'total': {
                            'baseline': {'2009': 3720, '2010': 3720},
                            'efficient': {'2009': 2232, '2010': 2232}},
                        'competed': {
                            'baseline': {'2009': 1860, '2010': 1860},
                            'efficient': {'2009': 372, '2010': 372}}},
                    'cost': {
                        'stock': {
                            'total': {
                                'baseline': {'2009': 340, '2010': 340},
                                'efficient': {'2009': 612, '2010': 612}},
                            'competed': {
                                'baseline': {'2009': 340, '2010': 340},
                                'efficient': {'2009': 612, '2010': 612}}},
                        'energy': {
                            'total': {
                                'baseline': {'2009': 680, '2010': 680},
                                'efficient': {'2009': 408, '2010': 408}},
                            'competed': {
                                'baseline': {'2009': 340, '2010': 340},
                                'efficient': {'2009': 68, '2010': 68}}},
                        'carbon': {
                            'total': {
                                'baseline': {'2009': 1020, '2010': 1020},
                                'efficient': {'2009': 612, '2010': 612}},
                            'competed': {
                                'baseline': {'2009': 510, '2010': 510},
                                'efficient': {'2009': 102, '2010': 102}}}},
                        "lifetime": {
                            "baseline": {'2010': (41 / 1240),
                                         '2009': (41 / 1240)},
                            "measure": 13.29}},
                "mseg_adjust": {
                    "contributing mseg keys and values": {
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'electricity',"
                         "'lighting', 'reflector (halogen)', 'existing')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 100, "2010": 100},
                                    "measure": {"2009": 60, "2010": 60}},
                                "competed": {
                                    "all": {"2009": 50, "2010": 50},
                                    "measure": {"2009": 10, "2010": 10}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 120, "2010": 120}},
                                "competed": {
                                    "baseline": {"2009": 100, "2010": 100},
                                    "efficient": {"2009": 20, "2010": 20}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 300, "2010": 300},
                                    "efficient": {"2009": 180, "2010": 180}},
                                "competed": {
                                    "baseline": {"2009": 150, "2010": 150},
                                    "efficient": {"2009": 30, "2010": 30}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}}},
                            "lifetime": {
                                "baseline": {"2009": 2, "2010": 2},
                                "measure": 15},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ5', 'single family home', "
                         "'electricity',"
                         "'cooling', 'supply', 'ASHP', 'new')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 1000, "2010": 1000},
                                    "measure": {"2009": 600, "2010": 600}},
                                "competed": {
                                    "all": {"2009": 500, "2010": 500},
                                    "measure": {"2009": 100, "2010": 100}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 2000, "2010": 2000},
                                    "efficient": {"2009": 1200, "2010": 1200}},
                                "competed": {
                                    "baseline": {"2009": 1000, "2010": 1000},
                                    "efficient": {"2009": 200, "2010": 200}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 3000, "2010": 3000},
                                    "efficient": {"2009": 1800, "2010": 1800}},
                                "competed": {
                                    "baseline": {"2009": 1500, "2010": 1500},
                                    "efficient": {"2009": 300, "2010": 300}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}}},
                            "lifetime": {
                                "baseline": {"2009": 18, "2010": 18},
                                "measure": 18},
                            "sub-market scaling": 1}},
                    "competed choice parameters": {
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'electricity',"
                         "'lighting', 'reflector (incandescent)', "
                         "'existing')"): {
                            "b1": {"2009": 0.25, "2010": 0.25},
                            "b2": {"2009": 0.25, "2010": 0.25}},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'electricity',"
                         "'lighting', 'reflector (halogen)', "
                         "'existing')"): {
                            "b1": {"2009": 0.25, "2010": 0.25},
                            "b2": {"2009": 0.25, "2010": 0.25}},
                        ("('primary', AIA_CZ5', 'single family home', "
                         "'electricity',"
                         "'cooling', 'supply', 'ASHP', 'new')"): {
                            "b1": {"2009": 0.75, "2010": 0.75},
                            "b2": {"2009": 0.75, "2010": 0.75}}},
                    "secondary mseg adjustments": {
                        "sub-market": {
                            "original energy (total)": {},
                            "adjusted energy (sub-market)": {}},
                        "stock-and-flow": {
                            "original energy (total)": {},
                            "adjusted energy (previously captured)": {},
                            "adjusted energy (competed)": {},
                            "adjusted energy (competed and captured)": {}},
                        "market share": {
                            "original energy (total captured)": {},
                            "original energy (competed and captured)": {},
                            "adjusted energy (total captured)": {},
                            "adjusted energy (competed and captured)": {}}}},
                "mseg_out_break": {
                    'AIA CZ1': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {},
                            'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0.016, "2010": 0.016},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {},
                            'Ventilation': {},
                            'Lighting': {
                                "2009": 0.5510753,
                                "2010": 0.5510753},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0, "2010": 0},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ2': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0.016, "2010": 0.016},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0, "2010": 0},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ3': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ4': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ5': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {
                                "2009": 0.4166667, "2010": 0.4166667},
                            'Ventilation': {}, 'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {},
                            'Ventilation': {}, 'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}}}},
            "Max adoption potential": {
                "master_mseg": {
                    'stock': {
                        'total': {
                            'all': {'2009': 1240, '2010': 1240},
                            'measure': {'2009': 744, '2010': 744}},
                        'competed': {
                            'all': {'2009': 620, '2010': 620},
                            'measure': {'2009': 124, '2010': 124}}},
                    'energy': {
                        'total': {
                            'baseline': {'2009': 2480, '2010': 2480},
                            'efficient': {'2009': 1488, '2010': 1488}},
                        'competed': {
                            'baseline': {'2009': 1240, '2010': 1240},
                            'efficient': {'2009': 248, '2010': 248}}},
                    'carbon': {
                        'total': {
                            'baseline': {'2009': 3720, '2010': 3720},
                            'efficient': {'2009': 2232, '2010': 2232}},
                        'competed': {
                            'baseline': {'2009': 1860, '2010': 1860},
                            'efficient': {'2009': 372, '2010': 372}}},
                    'cost': {
                        'stock': {
                            'total': {
                                'baseline': {'2009': 340, '2010': 340},
                                'efficient': {'2009': 612, '2010': 612}},
                            'competed': {
                                'baseline': {'2009': 340, '2010': 340},
                                'efficient': {'2009': 612, '2010': 612}}},
                        'energy': {
                            'total': {
                                'baseline': {'2009': 680, '2010': 680},
                                'efficient': {'2009': 408, '2010': 408}},
                            'competed': {
                                'baseline': {'2009': 340, '2010': 340},
                                'efficient': {'2009': 68, '2010': 68}}},
                        'carbon': {
                            'total': {
                                'baseline': {'2009': 1020, '2010': 1020},
                                'efficient': {'2009': 612, '2010': 612}},
                            'competed': {
                                'baseline': {'2009': 510, '2010': 510},
                                'efficient': {'2009': 102, '2010': 102}}}},
                        "lifetime": {
                            "baseline": {'2010': (41 / 1240),
                                         '2009': (41 / 1240)},
                            "measure": 13.29}},
                "mseg_adjust": {
                    "contributing mseg keys and values": {
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 10, "2010": 10},
                                    "measure": {"2009": 6, "2010": 6}},
                                "competed": {
                                    "all": {"2009": 5, "2010": 5},
                                    "measure": {"2009": 1, "2010": 1}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 20, "2010": 20},
                                    "efficient": {"2009": 12, "2010": 12}},
                                "competed": {
                                    "baseline": {"2009": 10, "2010": 10},
                                    "efficient": {"2009": 2, "2010": 2}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 30, "2010": 30},
                                    "efficient": {"2009": 18, "2010": 18}},
                                "competed": {
                                    "baseline": {"2009": 15, "2010": 15},
                                    "efficient": {"2009": 3, "2010": 3}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {
                                            "2009": 18, "2010": 18}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 20, "2010": 20},
                                        "efficient": {"2009": 12, "2010": 12}},
                                    "competed": {
                                        "baseline": {"2009": 10, "2010": 10},
                                        "efficient": {"2009": 2, "2010": 2}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 30, "2010": 30},
                                        "efficient": {"2009": 18, "2010": 18}},
                                    "competed": {
                                        "baseline": {"2009": 15, "2010": 15},
                                        "efficient": {"2009": 3, "2010": 3}}}},
                            "lifetime": {
                                "baseline": {"2009": 5, "2010": 5},
                                "measure": 10},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ1', 'single family home', "
                             "'electricity',"
                             "'lighting', 'reflector (incandescent)', "
                             "'existing')"): {
                                "stock": {
                                    "total": {
                                        "all": {"2009": 100, "2010": 100},
                                        "measure": {"2009": 60, "2010": 60}},
                                    "competed": {
                                        "all": {"2009": 50, "2010": 50},
                                        "measure": {"2009": 10, "2010": 10}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}},
                                "cost": {
                                    "stock": {
                                        "total": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 180, "2010": 180}}},
                                    "energy": {
                                        "total": {
                                            "baseline": {
                                                "2009": 200, "2010": 200},
                                            "efficient": {
                                                "2009": 120, "2010": 120}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 100, "2010": 100},
                                            "efficient": {
                                                "2009": 20, "2010": 20}}},
                                    "carbon": {
                                        "total": {
                                            "baseline": {
                                                "2009": 300, "2010": 300},
                                            "efficient": {
                                                "2009": 180, "2010": 180}},
                                        "competed": {
                                            "baseline": {
                                                "2009": 150, "2010": 150},
                                            "efficient": {
                                                "2009": 30, "2010": 30}}}},
                                "lifetime": {
                                    "baseline": {"2009": 1, "2010": 1},
                                    "measure": 20},
                                "sub-market scaling": 1},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'electricity',"
                         "'lighting', 'reflector (halogen)', 'existing')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 100, "2010": 100},
                                    "measure": {"2009": 60, "2010": 60}},
                                "competed": {
                                    "all": {"2009": 50, "2010": 50},
                                    "measure": {"2009": 10, "2010": 10}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 200, "2010": 200},
                                    "efficient": {"2009": 120, "2010": 120}},
                                "competed": {
                                    "baseline": {"2009": 100, "2010": 100},
                                    "efficient": {"2009": 20, "2010": 20}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 300, "2010": 300},
                                    "efficient": {"2009": 180, "2010": 180}},
                                "competed": {
                                    "baseline": {"2009": 150, "2010": 150},
                                    "efficient": {"2009": 30, "2010": 30}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}}},
                            "lifetime": {
                                "baseline": {"2009": 2, "2010": 2},
                                "measure": 15},
                            "sub-market scaling": 1},
                        ("('primary', AIA_CZ5', 'single family home', "
                         "'electricity',"
                         "'cooling', 'supply', 'ASHP', 'new')"): {
                            "stock": {
                                "total": {
                                    "all": {"2009": 1000, "2010": 1000},
                                    "measure": {"2009": 600, "2010": 600}},
                                "competed": {
                                    "all": {"2009": 500, "2010": 500},
                                    "measure": {"2009": 100, "2010": 100}}},
                            "energy": {
                                "total": {
                                    "baseline": {"2009": 2000, "2010": 2000},
                                    "efficient": {"2009": 1200, "2010": 1200}},
                                "competed": {
                                    "baseline": {"2009": 1000, "2010": 1000},
                                    "efficient": {"2009": 200, "2010": 200}}},
                            "carbon": {
                                "total": {
                                    "baseline": {"2009": 3000, "2010": 3000},
                                    "efficient": {"2009": 1800, "2010": 1800}},
                                "competed": {
                                    "baseline": {"2009": 1500, "2010": 1500},
                                    "efficient": {"2009": 300, "2010": 300}}},
                            "cost": {
                                "stock": {
                                    "total": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 180, "2010": 180}}},
                                "energy": {
                                    "total": {
                                        "baseline": {"2009": 200, "2010": 200},
                                        "efficient": {
                                            "2009": 120, "2010": 120}},
                                    "competed": {
                                        "baseline": {"2009": 100, "2010": 100},
                                        "efficient": {
                                            "2009": 20, "2010": 20}}},
                                "carbon": {
                                    "total": {
                                        "baseline": {"2009": 300, "2010": 300},
                                        "efficient": {
                                            "2009": 180, "2010": 180}},
                                    "competed": {
                                        "baseline": {"2009": 150, "2010": 150},
                                        "efficient": {
                                            "2009": 30, "2010": 30}}}},
                            "lifetime": {
                                "baseline": {"2009": 18, "2010": 18},
                                "measure": 18},
                            "sub-market scaling": 1}},
                    "competed choice parameters": {
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, 'new')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ2', 'single family home', "
                         "'natural gas', 'water heating', None, "
                         "'existing')"): {
                            "b1": {"2009": 0.5, "2010": 0.5},
                            "b2": {"2009": 0.5, "2010": 0.5}},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'electricity',"
                         "'lighting', 'reflector (incandescent)', "
                         "'existing')"): {
                            "b1": {"2009": 0.25, "2010": 0.25},
                            "b2": {"2009": 0.25, "2010": 0.25}},
                        ("('primary', AIA_CZ1', 'single family home', "
                         "'electricity',"
                         "'lighting', 'reflector (halogen)', "
                         "'existing')"): {
                            "b1": {"2009": 0.25, "2010": 0.25},
                            "b2": {"2009": 0.25, "2010": 0.25}},
                        ("('primary', AIA_CZ5', 'single family home', "
                         "'electricity',"
                         "'cooling', 'supply', 'ASHP', 'new')"): {
                            "b1": {"2009": 0.75, "2010": 0.75},
                            "b2": {"2009": 0.75, "2010": 0.75}}},
                    "secondary mseg adjustments": {
                        "sub-market": {
                            "original energy (total)": {},
                            "adjusted energy (sub-market)": {}},
                        "stock-and-flow": {
                            "original energy (total)": {},
                            "adjusted energy (previously captured)": {},
                            "adjusted energy (competed)": {},
                            "adjusted energy (competed and captured)": {}},
                        "market share": {
                            "original energy (total captured)": {},
                            "original energy (competed and captured)": {},
                            "adjusted energy (total captured)": {},
                            "adjusted energy (competed and captured)": {}}}},
                "mseg_out_break": {
                    'AIA CZ1': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {},
                            'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0.016, "2010": 0.016},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {},
                            'Ventilation': {},
                            'Lighting': {
                                "2009": 0.5510753,
                                "2010": 0.5510753},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0, "2010": 0},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ2': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0.016, "2010": 0.016},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {"2009": 0, "2010": 0},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ3': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ4': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}},
                    'AIA CZ5': {
                        'Residential (New)': {
                            'Cooling (Equip.)': {
                                "2009": 0.4166667, "2010": 0.4166667},
                            'Ventilation': {}, 'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Residential (Existing)': {
                            'Cooling (Equip.)': {},
                            'Ventilation': {}, 'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (New)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}},
                        'Commercial (Existing)': {
                            'Cooling (Equip.)': {}, 'Ventilation': {},
                            'Lighting': {},
                            'Refrigeration': {}, 'Other': {},
                            'Water Heating': {},
                            'Computers and Electronics': {},
                            'Heating (Equip.)': {}, 'Envelope': {}}}}}}
        cls.mseg_ok_in_test2 = {
            "stock": {
                "total": {
                    "all": {"2009": 40, "2010": 40},
                    "measure": {"2009": 24, "2010": 24}},
                "competed": {
                    "all": {"2009": 20, "2010": 20},
                    "measure": {"2009": 4, "2010": 4}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 80, "2010": 80},
                    "efficient": {"2009": 48, "2010": 48}},
                "competed": {
                    "baseline": {"2009": 40, "2010": 40},
                    "efficient": {"2009": 8, "2010": 8}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 120, "2010": 120},
                    "efficient": {"2009": 72, "2010": 72}},
                "competed": {
                    "baseline": {"2009": 60, "2010": 60},
                    "efficient": {"2009": 12, "2010": 12}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 40, "2010": 40},
                        "efficient": {"2009": 72, "2010": 72}},
                    "competed": {
                        "baseline": {"2009": 40, "2010": 40},
                        "efficient": {"2009": 72, "2010": 72}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 80, "2010": 80},
                        "efficient": {"2009": 48, "2010": 48}},
                    "competed": {
                        "baseline": {"2009": 40, "2010": 40},
                        "efficient": {"2009": 8, "2010": 8}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 120, "2010": 120},
                        "efficient": {"2009": 72, "2010": 72}},
                    "competed": {
                        "baseline": {"2009": 60, "2010": 60},
                        "efficient": {"2009": 12, "2010": 12}}}},
            "lifetime": {
                "baseline": {"2009": 5, "2010": 5},
                "measure": 10}}
        cls.mseg_ok_out_test2 = {
            "stock": {
                "total": {
                    "all": {"2009": 40, "2010": 40},
                    "measure": {"2009": 24, "2010": 24}},
                "competed": {
                    "all": {"2009": 20, "2010": 20},
                    "measure": {"2009": 4, "2010": 4}}},
            "energy": {
                "total": {
                    "baseline": {"2009": 80, "2010": 80},
                    "efficient": {"2009": 38.4, "2010": 38.4}},
                "competed": {
                    "baseline": {"2009": 40, "2010": 40},
                    "efficient": {"2009": 0, "2010": 0}}},
            "carbon": {
                "total": {
                    "baseline": {"2009": 120, "2010": 120},
                    "efficient": {"2009": 57.6, "2010": 57.6}},
                "competed": {
                    "baseline": {"2009": 60, "2010": 60},
                    "efficient": {"2009": 0, "2010": 0}}},
            "cost": {
                "stock": {
                    "total": {
                        "baseline": {"2009": 40, "2010": 40},
                        "efficient": {"2009": 57.6, "2010": 57.6}},
                    "competed": {
                        "baseline": {"2009": 40, "2010": 40},
                        "efficient": {"2009": 57.6, "2010": 57.6}}},
                "energy": {
                    "total": {
                        "baseline": {"2009": 80, "2010": 80},
                        "efficient": {"2009": 38.4, "2010": 38.4}},
                    "competed": {
                        "baseline": {"2009": 40, "2010": 40},
                        "efficient": {"2009": 0, "2010": 0}}},
                "carbon": {
                    "total": {
                        "baseline": {"2009": 120, "2010": 120},
                        "efficient": {"2009": 57.6, "2010": 57.6}},
                    "competed": {
                        "baseline": {"2009": 60, "2010": 60},
                        "efficient": {"2009": 0, "2010": 0}}}},
            "lifetime": {
                "baseline": {"2009": 5, "2010": 5},
                "measure": 10}}

    def test_merge_measure(self):
        """Test 'merge_measures' function given valid inputs."""
        self.sample_package_in_test1.merge_measures()
        # Check for correct general attributes for packaged measure
        output_lists = [
            self.sample_package_in_test1.name,
            self.sample_package_in_test1.climate_zone,
            self.sample_package_in_test1.bldg_type,
            self.sample_package_in_test1.structure_type,
            self.sample_package_in_test1.fuel_type,
            self.sample_package_in_test1.end_use["primary"]]
        for ind in range(0, len(output_lists)):
            self.assertEqual(sorted(self.genattr_ok_out_test1[ind]),
                             sorted(output_lists[ind]))
        # Check for correct markets for packaged measure
        self.dict_check(
            self.sample_package_in_test1.markets, self.markets_ok_out_test1)

    def test_apply_pkg_benefits(self):
        """Test 'apply_pkg_benefits' function given valid inputs."""
        self.dict_check(
            self.sample_package_in_test2.apply_pkg_benefits(
                self.mseg_ok_in_test2),
            self.mseg_ok_out_test2)


class CleanUpTest(unittest.TestCase, CommonMethods):
    """Test 'split_clean_data' function.

    Ensure building vintage square footages are read in properly from a
    cbecs data file and that the proper weights are derived for mapping
    EnergyPlus building vintages to Scout's 'new' and 'retrofit' building
    structure types.

    Attributes:
        handyvars (object): Global variables to use for the test measure.
        sample_measlist_in (list): List of individual and packaged measure
            objects to clean up.
        sample_measlist_out_comp_data (list): Measure competition data that
            should be yielded by function given sample measures as input.
        sample_measlist_out_mkt_keys (list): High level measure summary data
            keys that should be yielded by function given sample measures as
            input.
        sample_measlist_out_highlev_keys (list): Measure 'markets' keys that
            should be yielded by function given sample measures as input.
        sample_pkg_meas_names (list): Updated 'contributing_ECMs'
            attribute that should be yielded by function for sample
            packaged measure.
    """

    @classmethod
    def setUpClass(cls):
        """Define variables and objects for use across all class functions."""
        # Base directory
        base_dir = os.getcwd()
        benefits = {
            "energy savings increase": None,
            "cost reduction": None}
        cls.handyvars = ecm_prep.UsefulVars(base_dir,
                                            ecm_prep.UsefulInputFiles())
        sample_measindiv_dicts = [{
            "name": "cleanup 1",
            "market_entry_year": None,
            "market_exit_year": None,
            "measure_type": "full service",
            "technology": {
                "primary": None, "secondary": None}},
            {
            "name": "cleanup 2",
            "market_entry_year": None,
            "market_exit_year": None,
            "measure_type": "full service",
            "technology": {
                "primary": None, "secondary": None}}]
        cls.sample_measlist_in = [ecm_prep.Measure(
            cls.handyvars, **x) for x in sample_measindiv_dicts]
        sample_measpackage = ecm_prep.MeasurePackage(
            copy.deepcopy(cls.sample_measlist_in), "cleanup 3",
            benefits, cls.handyvars)
        cls.sample_measlist_in.append(sample_measpackage)
        cls.sample_measlist_out_comp_data = [{
            "Technical potential": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}},
            "Max adoption potential": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}}},
            {
            "Technical potential": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}},
            "Max adoption potential": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}}},
            {
            "Technical potential": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}},
            "Max adoption potential": {
                "contributing mseg keys and values": {},
                "competed choice parameters": {},
                "secondary mseg adjustments": {
                    "market share": {
                        "original energy (total captured)": {},
                        "original energy (competed and captured)": {},
                        "adjusted energy (total captured)": {},
                        "adjusted energy (competed and captured)": {}}}}}]
        cls.sample_measlist_out_mkt_keys = ["master_mseg", "mseg_out_break"]
        cls.sample_measlist_out_highlev_keys = [
            ["market_entry_year", "market_exit_year", "markets",
             "name", "out_break_norm", "remove", 'technology',
             'technology_type', 'yrs_on_mkt', 'measure_type'],
            ["market_entry_year", "market_exit_year", "markets",
             "name", "out_break_norm", "remove", 'technology',
             'technology_type', 'yrs_on_mkt', 'measure_type'],
            ['benefits', 'bldg_type', 'climate_zone', 'end_use', 'fuel_type',
             "technology", "technology_type",
             "market_entry_year", "market_exit_year", 'markets',
             'contributing_ECMs', 'name', "out_break_norm", 'remove',
             'structure_type', 'yrs_on_mkt', 'measure_type']]
        cls.sample_pkg_meas_names = [x["name"] for x in sample_measindiv_dicts]

    def test_cleanup(self):
        """Test 'split_clean_data' function given valid inputs."""
        # Execute the function
        measures_comp_data, measures_summary_data = \
            ecm_prep.split_clean_data(self.sample_measlist_in)
        # Check function outputs
        for ind in range(0, len(self.sample_measlist_in)):
            # Check measure competition data
            self.dict_check(self.sample_measlist_out_comp_data[ind],
                            measures_comp_data[ind])
            # Check measure summary data
            for adopt_scheme in self.handyvars.adopt_schemes:
                self.assertEqual(sorted(list(measures_summary_data[
                    ind].keys())),
                    sorted(self.sample_measlist_out_highlev_keys[ind]))
                self.assertEqual(sorted(list(measures_summary_data[
                    ind]["markets"][adopt_scheme].keys())),
                    sorted(self.sample_measlist_out_mkt_keys))
                # Verify correct updating of 'contributing_ECMs'
                # MeasurePackage attribute
                if "Package: " in measures_summary_data[ind]["name"]:
                    self.assertEqual(measures_summary_data[ind][
                        "contributing_ECMs"], self.sample_pkg_meas_names)


# Offer external code execution (include all lines below this point in all
# test files)
def main():
    """Trigger default behavior of running all test fixtures in the file."""
    unittest.main()


if __name__ == "__main__":
    main()
