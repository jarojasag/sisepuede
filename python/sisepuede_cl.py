# 
#  COMMAND LINE RUNTIME FOR SISEPUEDE
#
# NOTE NOTE: SHOULD START WITH JULIA_NUM_THREADS=XX TO SET THREADS ACCESSIBLE TO JULIA WHEN RUNNING NemoMod
#  
#
import argparse
from model_attributes import ModelAttributes
import numpy as np
import os, os.path
import pandas as pd
import sisepuede as ssp
import sisepuede_file_structure as sfs
import support_classes as sc
import support_functions as sf
from typing import *
import warnings


###################################
#    SOME SUPPORTING FUNCTIONS    #
###################################

def get_models(
    models: str,
    model_attributes: ModelAttributes,
    delim: str = ",",
) -> Union[List[str], str, None]:
    """
    Return list of regions to run. Splits argument with delimiter `delim`
    """
    # if invalid, return a list of length 0
    if not isinstance(models, str):
        return None

    # fed to SISEPUEDE; if None, then it will instantiate all regions
    if models.upper() == "ALL":
        return None

    attr_subsector = model_attributes.dict_attributes.get("abbreviation_sector")
    valid_models = attr_subsector.key_values + list(attr_subsector.table["sector"])

    models = [
        x for x in models.split(delim)
        if x in valid_models
    ]

    return models



def get_regions(
    region_args: str,
    regions_obj: sc.Regions,
    delim: str = ",",
) -> Union[List[str], str, None]:
    """
    Return list of regions to run. Splits argument with delimiter `delim`
    """
    # if invalid, return a list of length 0
    if not isinstance(region_args, str):
        return []

    # fed to SISEPUEDE; if None, then it will instantiate all regions
    if region_args == "ALLREGIONS":
        return None

    regions = get_dimensional_values(
        region_args, 
        regions_obj.key,
        delim = delim,
        return_type = str,
    )
    regions = [
        regions_obj.return_region_or_iso(x, return_type = "region")
        for x in regions
    ]

    regions = [x for x in regions if x is not None]

    return regions



def get_dimensional_dict(
    args: Dict,
    model_attributes: ModelAttributes,
    cl_key_design: str = "keys_design",
    cl_key_future: str = "keys_future",
    cl_key_primary: str = "keys_primary",
    cl_key_strategy: str = "keys_strategy",
) -> Union[Dict, None]:
    """
    From args, get dimensional keys. Use model_attributes to assign.
    """
    
    if not isinstance(args, dict):
        return None
    

    # initialize dictionary mapping command-line key to sisepuede key
    dict_key_map = {
        cl_key_design: model_attributes.dim_design_id,
        cl_key_future: model_attributes.dim_future_id,
        cl_key_primary: model_attributes.dim_primary_id,
        cl_key_strategy: model_attributes.dim_strategy_id
    }

    # initialize dictionary
    dict_out = {}

    if args.get(cl_key_primary) is not None:
        key = dict_key_map.get(cl_key_primary)
        vals = get_dimensional_values(args.get(cl_key_primary), key)
        (
            dict_out.update({key: vals})
            if vals is not None
            else None
        )

    else:
        for k in [cl_key_design, cl_key_future, cl_key_strategy]:
            key = dict_key_map.get(k)
            vals = get_dimensional_values(args.get(k), key)
            (
                dict_out.update({key: vals})
                if vals is not None
                else None
            )

    dict_out =(
        None
        if len(dict_out) == 0
        else dict_out
    )

    return dict_out



def get_dimensional_values(
    keys_in: str,
    key: str,
    delim: str = ",",
    return_type: type = int,
) -> List[int]:
    """
    Read in dimensional values. `keys_in` can be a list of values separated by
        `delim`, or a path to a text file--the text file will be read as a data
        frame and must contain column header key.
    """

    values = None

    if not isinstance(keys_in, str):
        return None

    if os.path.exists(keys_in):
        try:
            df = pd.read_csv(keys_in)
        except Exception as e:
            raise RuntimeError(f"Error trying to read keys from file {keys_in}: {e}")
        
        if key not in df.columns:
            raise RuntimeError(f"Error reading keys from file {keys_in}: key '{key}' not found in the file.")
        
        values = [return_type(x) for x in list(df[key])]

    elif isinstance(keys_in, str):
        try:
            values = [return_type(x) for x in keys_in.split(delim)]
        except Exception as e:
            raise RuntimeError(f"Error trying to read keys in input string: {e}")

    return values



def parse_arguments() -> dict:

    desc = f"""
    Command line utility to run SImulating SEctoral Pathways and Uncertainty 
        Exploration for DEcarbonization (SISEPUEDE). 

    Required arguments:
    -------------------
    --regions   Comma-delimitted list of regions to run. Regions can be entered 
                    as region names or ISO codes. E.g., BRA,CHL,MEX is 
                    acceptable, as is brazil,chile,mexico. 
                    
                    * To run all available regions (may take a significant 
                        amount of time), use ALLREGIONS.
    

    At Least ONE of the following arguments is required
    ---------------------------------------------------
    NOTE: if specifiying keys_primary and any of keys_design, keys_future, 
        or keys_strategy, key_primary will take precedence. Otherwise, runs all 
        scenarios that match *all* specifications of design, future, and/or 
        strategy (i.e., intersectional set logic).

    NOTE: Keys that are specified in a file must include the following rules:
        * If specifying as a file, the file must include each id on a new line
        * Non-numeric values are skipped
        * If specifying in a CSV, will try to read from the appropriate key

    --keys_design   Comma-delimited list of design ids to run  OR  a valid file 
                        path to a text file containing id numbers to run. Must
                        contain key SISEPUEDE.key_design, and ids must be 
                        defined in the attribute_design_id.csv ModelAttributes
                        source file.
    --keys_future   Comma-delimited list of future ids to run  OR  a valid file 
                        path to a text file containing id numbers to run. Must
                        contain key SISEPUEDE.key_future, and ids x must be 
                        0 <= x <= n_trials (0 is a null trial)
    --keys_primary  Comma-delimited list of primary ids to run  OR  a valid file 
                        path to a text file containing id numbers to run. 
    --keys_strategy Comma-delimited list of strategy ids to run  OR  a valid file 
                        path to a text file containing id numbers to run. Must
                        contain key SISEPUEDE.key_strategy, and ids x must be 
                        defined in the attribute_strategy_id.csv ModelAttributes 
                        source file.

    Optional arguments:
    -------------------
    --id            Optional AnalysisID name to pass. If not specified, sets at 
                        runtime.
    --max-solve-attempts   Maximum number of attempts to solve a problem. Only
                        retries if emissions values indicate potential numerical
                        issues with the solution.
    --n_trials      Number of Latin Hypercube trials to run (number of 
                        futures, which represent exogenous uncertainties and/or
                        lever effect uncertainties)

    --random_seed   Optional random seed to specify. If not specifed, 
                        defaults to configuration specifation. Enter a negative
                        number to generate on the fly.

    #####
	#
	# LICENSE INFORMATION 
	# -----------------------
	#
	# https://www.gnu.org/licenses/gpl-howto.html (use this )
	# GNU 3.0
	#
	#####

    """
    parser = argparse.ArgumentParser(
        description = ""
    )


    ##  REQUIRED ARGUMENTS

    # regions to run
    msg_hlp_regions = f"""
    Comma-delimited list of regions or ISO codes to run. Required argument. To
        run all available regions, set to ALLREGIONS
    """
    parser.add_argument(
        "--regions",
        help = msg_hlp_regions,
    )


    ##  AT LEAST ONE MUST BE SPECIFIED

    # design keys
    msg_hlp_key_design = f"""
    Comma-delimited list of design keys to read OR file path to table 
        containing list of key values (as rows)
    """
    parser.add_argument(
        "--keys-design",
        default = None,
        help = msg_hlp_key_design,
        type = str,
    )


    # future keys
    msg_hlp_key_future = f"""
    Comma-delimited list of future keys to read OR file path to table 
        containing list of key values (as rows). Only those that are <= n_trials
        will be included.
    """
    parser.add_argument(
        "--keys-future",
        default = None,
        help = msg_hlp_key_future,
        type = str,
    )


    # primary keys
    msg_hlp_key_primary = f"""
    Comma-delimited list of primary keys to read OR file path to table 
        containing list of key values (as rows)
    """
    parser.add_argument(
        "--keys-primary",
        default = None,
        help = msg_hlp_key_primary,
        type = str,
    )


    # strategy keys
    msg_hlp_key_strategy = f"""
    Comma-delimited list of strategy keys to read OR file path to table 
        containing list of key values (as rows)
    """
    parser.add_argument(
        "--keys-strategy",
        default = None,
        help = msg_hlp_key_strategy,
        type = str,
    )



    ##  OPTIONAL ARGUMENTS/FLAGS

    # optional database type specification
    msg_hlp_db_type = f"""
    Optional specification of output database type (str). Default is sqlite. 
        Acceptable options are "csv" and "sqlite"
    """
    parser.add_argument(
        "--database-type",
        type = str,
        help = msg_hlp_db_type,
        default = "sqlite",
    )


    # optional flag to *exclude* electricity model 
    msg_hlp_exclude_fuel_prod = f"""
    Exclude the fuel production (NemoMod) model from runs. 
    """
    parser.add_argument(
        "--exclude-fuel-production",
        action = "store_true",
        help = msg_hlp_exclude_fuel_prod,
    )


    # optional AnalysisID string to pass
    msg_hlp_id = f"""
    Optinal id to pass on instantiation.
    """
    parser.add_argument(
        "--id",
        default = None,
        help = msg_hlp_id,
        type = str,
    )


    # optional flag for number of trials
    msg_hlp_n_trials = f"""
    Specify the number of Latin Hypercube trials to run (number of futures, 
        which represent exogenous uncertainties and/or lever effect
        uncertainties). If unspecified, defaults to configuration value.
    """
    parser.add_argument(
        "--n-trials",
        help = msg_hlp_n_trials,
        type = int,
        default = None,
    )


    # optional flag for models to include
    msg_hlp_max_solve_attempts = f"""
    Maximum number of times to attempt solving a problem due to numerical 
        instability or solve issues. Default is 2.
    """
    parser.add_argument(
        "--max-solve-attempts",
        type = int,
        help = msg_hlp_max_solve_attempts,
        default = 2,
    )


    # optional flag for models to include
    msg_hlp_models = f"""
    Optional flag used to specify models to run. Possible values include 'All' 
        (run all models [default]) or any comma-delimited combination of the 
        following: 
        
        * AFOLU, AF, or af
        * CircularEconomy, CE, or ce 
        * Energy, EN, or en
        * IPPU, IP, or ip

    NOTE: to turn off running the fuel production (electricity) model, use the 
        flag `--exclude-fuel-production`
    """
    parser.add_argument(
        "--models",
        type = str,
        help = msg_hlp_models,
        default = "All"
    )


    # optional random seed 
    msg_hlp_random_seed = f"""
    Optional random seed to specify for runs. If not specified, defaults to 
        configuration random seed. 
        
        * NOTE: To choose one randomly, set to a negative number.
    """
    parser.add_argument(
        "--random-seed",
        type = int,
        help = msg_hlp_random_seed,
        default = None
    )


    # optional save inputs
    msg_hlp_save_inputs = f"""
    Include the --save-inputs flag to save off inputs to the 
        SISEPUEDEOutputDatabase. In general, model inputs are not saved off to 
        reduce space requirements and can generally be accessed using
        SISEPUEDE.experimental_manager.dict_future_trajectories.get(region).generate_future_from_lhs_vector()
    """
    parser.add_argument(
        "--save-inputs",
        action = "store_true",
        help = msg_hlp_save_inputs,
    )

    

    if False:
        # optional input csv
        msg_hlp_from_input = f"""
        Path to an input CSV, long by time_period, that contains required input 
            variables. 
            
        NOTE: use with caution. This is approach is not-well checked
            and current implementation of error handling may be insufficient.
        """
        parser.add_argument(
            "--from-input",
            type = str,
            help = msg_hlp_from_input,
            default = None,
        )


        # optional output csv
        msg_hlp_from_input = f"""
        Path to an output CSV, long by time_period. Only used it --from-input is 
            specified.
        """
        parser.add_argument(
            "--to-output",
            type = str,
            help = msg_hlp_from_input,
            default = None,
        )


    ##  PARSE ARGUMENTS

    parsed_args = parser.parse_args()

    # Since defaults are env vars, still need to checking to make sure its passed
    errors = []
    if parsed_args.regions is None:
        errors.append(
            "Missing --regions argument. Use --regions ALLREGIONS to run all available regions."
        )
    
    if errors:
        raise ValueError(f"Missing arguments detected: {sf.format_print_list(errors)}")

    # json args over-write specified args
    parsed_args_as_dict = vars(parsed_args)

    return parsed_args_as_dict





def main(
    args: dict,
) -> None:
    """
    Run SISEPUEDE from the command line
    """

    warnings.filterwarnings("ignore")

    # get file structure to activate model attributes before instantiating SISEPUEDE
    file_struct = sfs.SISEPUEDEFileStructure()
    regions_obj = sc.Regions(file_struct.model_attributes)


    ##  1. GET INPUTS

    # models
    models = get_models(args.get("models"), file_struct.model_attributes)

    # regions
    regions_run = get_regions(
        args.get("regions"),
        regions_obj,
        delim = ",",
    )

    # scenario information
    dict_scenarios = get_dimensional_dict(
        args, 
        file_struct.model_attributes
    )
    if dict_scenarios is None:
        msg = f"""
        No valid dimensional subsets or scenarios were specified. Ensure that 
            either primary_id OR any combination of design_id, future_id, and/or
            straetgy_id are specified.
        """
        raise RuntimeError(msg)
        return None

    # additional parameters
    db_type = args.get("database_type")
    db_type = "sqlite" if (db_type not in ["sqlite", "csv"]) else db_type
    id_str = args.get("id")

    include_fuel_prod = (not args.get("exclude_fuel_production"))
    max_solve_attempts = args.get("max_solve_attempts")
    n_trials = args.get("n_trials")
    random_seed = args.get("random_seed")
    save_inputs = args.get("save_inputs")

    # checks
    return_none = (regions_run is None)
    return_none |= ((len(dict_scenarios) == 0) if not return_none else False)
    return_none |= (dict_scenarios is None)

    if return_none:
        raise RuntimeError("Invalid specification of regions, input dimensions. Check arguments and try again")
        return None


    ##  2. INITIALIZE SISEPUEDE AND RUN

    sisepuede = ssp.SISEPUEDE(
        "calibrated",
        db_type = db_type,
        id_str = id_str,
        n_trials = n_trials,
        random_seed = random_seed,
        regions = regions_run,
    )

    dict_primaries_complete = sisepuede(
        dict_scenarios,
        chunk_size = 2,
        check_results = True,
        include_electricity_in_energy = include_fuel_prod,
        max_attempts = max_solve_attempts,
        reinitialize_output_table_on_verification_failure = True,
        save_inputs = save_inputs,
    )

    sisepuede._log(
        f"SISEPUEDE run '{sisepuede.id}' complete.", 
        type_log = "info"
    )

    return 0

    

if __name__ == "__main__":

    args = parse_arguments()
        
    main(args)
    
