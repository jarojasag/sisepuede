import logging
import munch
import numpy as np
import os, os.path
import pandas as pd
import re
import time
from typing import *
import yaml
import warnings



def add_data_frame_fields_from_dict(
    df: pd.DataFrame,
    dict_field_vals: dict,
    field_hierarchy: Union[None, list, np.ndarray] = None,
    overwrite_fields: bool = False,
    prepend_q: bool = True
) -> pd.DataFrame:
    """
    Inplace operator for adding fields to a dataframe.
        * New fields are entered as a key in `dict_field_vals`, and new values
            for the dataframe are entered as values
        * Values may be passed as a single value (e.g., str, int, float) or a
            vector (list/np.array)

    Function Arguments
    ------------------
    - df: DataFrame to add index fields to
    - dict_field_vals: dictionary mapping a new field (key) to value (value)

    Keyword Arguments
    -----------------
    - field_hierarchy: field hierachy (ordering) for new fields. Only used if
        `prepend_q` = True. If None, default to sorted()
    - overwrite_fields: for key in dict_field_vals.keys(), overwrite field `key`
        if present in `df`?
    - prepend_q: prepend the new fields to the data frame (ordered fields)
    """

    nms = list(df.columns)
    fields_add = []

    for key in dict_field_vals.keys():
        if (key not in nms) or overwrite_fields:
            val = dict_field_vals.get(key)
            if isinstance(val, list) or isinstance(val, np.ndarray):
                # chceck length
                if len(val) == len(df):
                    df[key] = val
                    fields_add.append(key)
                else:
                    warnings.warn(f"Unable to add key {key} to data from in add_data_frame_fields_from_dict() -- the vector associated with the value does not match the length of the data frame.")
            else:
                df[key] = val
                fields_add.append(key)
        elif (key in nms):
            warnings.warn(f"Field '{key}' found in dictionary in add_data_frame_fields_from_dict(). It will not be overwritten. ")
            fields_add.append(key)

    # order output fields
    fields_out = list(df.columns)
    if prepend_q:
        ordering_prepend = [x for x in field_hierarchy if x in fields_add] if (field_hierarchy is not None) else sorted(fields_add)
        ordering_append = [x for x in fields_out if x not in ordering_prepend]
        fields_out = ordering_prepend + ordering_append

    return df[fields_out]



def back_project_array(
    array_in: np.ndarray,
    n_periods: int = 10,
    bp_gr: float = 0.03,
    use_mean_forward: bool = False,
    n_periods_for_gr: int = 10
) -> np.ndarray:
    """
    "Project" backwards data based on near-future trends (used only in the 
        absence of historical data)

    Function Arguments
    ------------------
    - array_in: array to use for back projection

    Keyword Arguments
    -----------------
    - n_periods: number of periods to back project
    - bp_gr: float specifying the average growth rate for row entries during the 
        back projection periods
    - use_mean_forward: default is False. If True, use the average empirical 
        growth rate in array_in for the first 'n_periods_for_gr' periods
    - n_periods_for_gr: if use_mean_forward == True, number of periods to look 
        forward (rows 1:n_periods_for_gr)
    """

    if use_mean_forward:
        # get a mean growth rate
        n_periods_for_gr = max(min(n_periods_for_gr, len(array_in) - 1), 1)
        growth_scalars = array_in[1:(n_periods_for_gr + 1)]/array_in[0:(n_periods_for_gr)]
        vec_mu = np.mean(growth_scalars, axis = 0)
    else:
        vec_mu = (1 + bp_gr)*np.ones(len(array_in[0]))
    # set up an array of exponents
    array_exponent = -np.outer(n_periods - np.arange(n_periods), np.ones(len(vec_mu)))

    return (vec_mu**array_exponent)*array_in[0]



def build_dict(
    df_in: pd.DataFrame,
    dims = None,
    force_tuple = False,
    nan_to_none_keys = False,
    nan_to_none_vals = False
) -> dict:

    """
    Build a dictionary to map row-wise elements of df_in to other row-wise
        elements.
        * If dims is None, then df_in will map the first n - 1 columns (as a
            tuple) to the nth column

    Function Arguments
    ------------------
    - df_in: DataFrame used to build dictionary

    Keyword Arguments
    -----------------
    - dims: dims used to build dictionary
        * e.g., in 4-column data frame, can enter (2, 2) to map the first two
            columns [as a tuple] to the next two columns (as a tuple))
    - force_tuple: if True, force an individual element as a tuple
    - nan_to_none_keys: convert NaNs to None if True in keys
    - nan_to_none_vals: convert NaNs to None if True in values
    """

    if (len(df_in.columns) == 2) and not force_tuple:
        dict_out = dict([x for x in zip(df_in.iloc[:, 0], df_in.iloc[:, 1])])
    else:
        if dims == None:
            dims = (len(df_in.columns) - 1, 1)
        n_key = dims[0]
        n_val = dims[1]
        if n_key + n_val != len(df_in.columns):
            raise ValueError(f"Invalid dictionary dimensions {dims}: the sum of dims should be equal to the number of columns in the input dataframe ({len(df_in.columns)}). They sum to {n_key + n_val}.")

        # keys to zip
        if (n_key == 1) and not force_tuple:
            keys = df_in.iloc[:, 0]
        else:
            keys_in = np.array(df_in[list(df_in.columns)[0:n_key]])
            if nan_to_none_keys:
                keys = [None for x in range(keys_in.shape[0])]
                for i in range(len(keys)):
                    key = keys_in[i, :]
                    keys[i] = tuple([(None if (isinstance(x, float) and np.isnan(x)) else x) for x in key])

            else:
                keys = [tuple(x) for x in keys_in]

        # values to zip
        if n_val == 1:
            vals = np.array(df_in.iloc[:, len(df_in.columns) - 1])
        else:
            vals = [np.array(x) for x in np.array(df_in[list(df_in.columns)[n_key:(n_key + n_val)]])]
        #
        if nan_to_none_vals:
            vals = [(None if np.isnan(x) else x) for x in vals]

        dict_out = dict([x for x in zip(keys, vals)])

    return dict_out



def build_repeating_vec(
    vec: Union[list, np.ndarray],
    n_repetitions_inner: Union[int, None],
    n_repetitions_outer: Union[int, None],
    keep_index: Union[List[int], None] = None
) -> np.ndarray:
    """
    Build an array of repeating values, repeating elements an inner number of
        times (within the cycle) and an outer number of times (number of times
        to cycle).

    Function Arguments
    ------------------
    - vec: list or np.ndarray of values to repeat
    - n_repetitions_inner: number of inner repetitions. E.g., for a vector
        vec = [0, 1, 2], if n_repetitions_inner = 3, then the inner component
        (the component that is repeated an outer # of times) would be

        vec_inner = [0, 0, 0, 1, 1, 1, 2, 2, 2]

    - n_repetitions_outer: number of outer repetitions. E.g., for vec_inner from
        above, if n_repetitions_outer = 3, then the final output component would
        be

        vec = [0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 0, 0, 1, 1, 1, 2, 2, 2]

    Keyword Arguments
    -----------------
    - keep_index: optional argument specifying indices of the vector to keep
        (e.g., [0, 1, 5]). If None (default), returns entire vector).
    """

    try:
        vec = np.array(vec)
    except Exception as e:
        raise RuntimeException(f"Error trying to set vec in build_repeating_vec(): {e}")

    vec = vec if (len(vec.shape) == 1) else vec.flatten()
    vec_inner = np.repeat(vec, n_repetitions_inner)
    vec_outer = np.repeat(np.array([vec_inner]), n_repetitions_outer, axis = 0).flatten()

    if keep_index is not None:
        keep_index = [x for x in keep_index if x < len(vec_outer)]
        vec_outer = vec_outer[keep_index]

    return vec_outer



def check_binary_fields(
    df_in: pd.DataFrame,
    field: str
) -> pd.DataFrame:
    """
    Replace nas in a field with 0s
    """
    w1 = list(np.where(df_in[field].isna())[0])
    if len(w1) > 0:
        df_in[field].iloc[w1] = 0

    return df_in



def check_fields(
    df: pd.DataFrame,
    fields: list,
    msg_prepend: str = "Required fields: ",
    throw_error_q = True
) -> bool:
    """
    Check that the data frame `df` contains required fields `fields`.

    Keyword Arguments
    -----------------
    - msg_prepend: optional message to prepend to errors for tracking
    - throw_error_q: throw an error if fields not found? If False, returns Bool
    """
    s_fields_df = set(df.columns)
    s_fields_check = set(fields)
    if s_fields_check.issubset(s_fields_df):
        return True

    fields_missing = format_print_list(s_fields_check - s_fields_df)
    if throw_error_q:
        raise KeyError(f"{msg_prepend}{fields_missing} not found in the data frame.")

    return False



def check_keys(
    dict_in: dict,
    keys: list,
    throw_error_q: bool = True
) -> bool:
    """
    Check keys in `dict_in` to ensure that required keys `keys` are contained.

    Function Arguments
    ------------------
    - dict_in: dictionary to check keys in
    - keys: required keys

    Keyword Arguments
    -----------------
    - throw_error_q: Throw an error if any required keys are not found?
        * If `throw_error_q == True`, will throw an error if required keys
            are not found
        * If `throw_error_q == False`, returns False if required keys are
            not found

    """
    s_keys_dict = set(dict_in.keys())
    s_keys_check = set(keys)
    if s_keys_check.issubset(s_keys_dict):
        return True

    fields_missing = format_print_list(s_keys_check - s_keys_dict)
    msg = f"Required keys {fields_missing} not found in the dictionary."
    if throw_error_q:
        raise KeyError(msg)

    warnings.warn(msg)

    return False



def check_path(
    fp: str,
    create_q: bool = False,
    throw_error_q: bool = True
) -> str:
    """
    Check a file path `fp` and create it if `create_q == True`

    Function Arguments
    ------------------
    - fp: path (directory or file) to check
    Keyword Arguments
    -----------------
    - create_q: create a directory if it does not exist?
    - throw_error_q: Throw an error if any required keys are not found?
        * If `throw_error_q == True`, will throw an error if required keys
            are not found
        * If `throw_error_q == False`, returns False if required keys are
            not found
    """

    if os.path.exists(fp):
        return fp
    elif create_q:
        os.makedirs(fp, exist_ok = True)
        return fp
    else:
        msg = f"Path '{fp}' not found. It will not be created."
        if not throw_error_q:
            warnings.warn(msg)
            return None
        else:
            raise RuntimeError(msg)



def check_row_sums(
    array: np.ndarray,
    sum_restriction: float = 1,
    thresh_correction: float = 0.001,
    msg_pass: str = ""
) -> np.ndarray:
    """
    Check row sums to ensure they add to 1
    """
    sums = array.sum(axis = 1)
    max_diff = np.max(np.abs(sums - sum_restriction))

    if max_diff > thresh_correction:
        raise ValueError(f"Invalid row sums in array{msg_pass}. The maximum deviance is {max_diff}, which is greater than the threshold for correction.")

    arr_out = (array.transpose()/sums).transpose()

    return arr_out


def check_set_values(
    subset: set,
    superset: set,
    str_append: str = ""
) -> None:
    """
    Throw an error if `subset` is not contained within `superset`. Use 
        `str_append` for error tracking. 
    """
    if not set(subset).issubset(set(superset)):
        invalid_vals = list(set(subset) - set(superset))
        invalid_vals.sort()
        invalid_vals = format_print_list(invalid_vals)
        raise ValueError(f"Invalid values {invalid_vals} found{str_append}.")

    return None



def clean_field_names(
    nms: Union[list, pd.DataFrame],
    dict_repl: Union[dict, None] = None,
    dict_repl_update: Union[dict, None] = None,
) -> list:
    """
    Clean names of an input table to eliminate spaces/unwanted characters.

    Function Arguments
    ------------------
    - nms: vector of names to clean
    
    Keyword Arguments
    -----------------
    - dict_repl: optional dictionary to use for replacement. If None, defaults
        to internal replacement
    - dict_repl_update: optional dictionary to use to update internal dict_repl
    """

    dict_repl = (
        {
            "  ": " ", 
            " ": "_", 
            "$": "", 
            "\\": "", 
            "\$": "", 
            "`": "", 
            "-": "_", 
            ".": "_", 
            "\ufeff": "", 
            ":math:text": "", 
            "{": "", 
            "}": ""
        }
        if not isinstance(dict_repl, dict)
        else dict_repl
    )
    (
        dict_repl.update(dict_repl_update) 
        if (dict_repl_update is not None) 
        else None
    )

    # check return type
    return_df_q =  False
    if isinstance(nms, pd.DataFrame):
        df = nms
        nms = list(df.columns)
        return_df_q = True

    # get namses to clean, then loop
    nms = [str_replace(nm.lower(), dict_repl) for nm in nms]

    for i in range(len(nms)):
        nm = nms[i]
        # drop characters in front
        while (nm[0] in ["_", "-", "."]) and (len(nm) > 1):
            nm = nm[1:]
        # drop trailing characters
        while (nm[-1] in ["_", "-", "."]) and (len(nm) > 1):
            nm = nm[0:-1]
        nms[i] = nm

    if return_df_q:
        nms = df.rename(columns = dict(zip(list(df.columns), nms)))

    return nms



def date_shift(
    ym_tup: Tuple[int, int], 
    n_months: int
) -> Tuple[int, int]:
    """
    Shift a year/month pair ym_tup by n_months (can be positive or negative)
    """
    y = ym_tup[0]
    m = ym_tup[1]
    
    y_0 = y + (m - 1)/12
    y_frac = n_months/12
    y_1 = math.floor(y_0 + y_frac)
    
    m_1 = round((y_frac + y_0 - y_1)*12) + 1

    return (y_1, m_1)



def days_per_month(
    ym_tup: Tuple[int, int]
) -> int:
    """
    Enter a tuple `ym_tup = (year, month)` to return the number of days in that 
        month. 
    """
    year = ym_tup[0]
    month = ym_tup[1]
    
    dict_base = {
        1: 31,
        2: 28,
        3: 31,
        4: 30,
        5: 31, 
        6: 30, 
        7: 31, 
        8: 31,
        9: 30,
        10: 31, 
        11: 30, 
        12: 31
    }
    
    dict_base.update({2: 29}) if (year%4 == 0) else None
    
    return dict_base.get(month)



def df_to_tuples(
    df_in: pd.DataFrame,
    nan_to_none: bool = False
) -> List[Tuple]:
    """
    Convert a data frame to tuples. Set nan_to_none = True to replace nans with
        None in the tuples.
    """

    arr = np.array(df_in)
    if nan_to_none:
        list_out = [None for x in range(len(df_in))]
        for i in range(len(list_out)):
            list_out[i] = tuple(
                [(None if (isinstance(x, float) and np.isnan(x)) else x) for x in arr[i, :]]
            )
    else:
        list_out = [tuple(x) for x in arr]

    return list_out



def df_get_missing_fields_from_source_df(
    df_target: pd.DataFrame,
    df_source: pd.DataFrame,
    side: str = "right",
    column_vector: Union[List, None] = None
) -> pd.DataFrame:
    """
    Fill in fields that are in another dataframe the same number of rows. 

    Function Arguments
    ------------------
    - df_target: data frame to fill with values from df_source
    - df_course: data frame used to fill values in df_target

    Keyword Arguments
    -----------------
    - side: position to add columns from df_source to df_target. "right" and 
        "left" are acceptable values
    - column_vector: optional specification of first columns to order (e.g., 
        the output dataframe will have column ordering

        [cv_0, cv_1, ..., cv_{n - 1}, other_field_0, ...])

        where cv_i in column_vector and other_field_j are output fields not 
        contained in column_vector
    """

    if df_target.shape[0] != df_source.shape[0]:
        raise RuntimeError(f"Incompatible shape found in data frames; the target number of rows ({df_target.shape[0]}) should be the same as the source ({df_source.shape[0]}).")
    
    # concatenate
    flds_add = [x for x in df_source.columns if x not in df_target]

    # default 
    side = "right" if (side.lower() not in ["right", "left"]) else side.lower()
    lcat = (
        [df_target.reset_index(drop = True), df_source[flds_add].reset_index(drop = True)]
        if (side == "right")
        else [df_source[flds_add].reset_index(drop = True), df_target.reset_index(drop = True)]
    )
    df_out = pd.concat(lcat,  axis = 1)

    if isinstance(column_vector, list):
        flds_1 = [x for x in column_vector if (x in df_out.columns)]
        flds_2 = [x for x in df_out.columns if (x not in flds_1)]
        df_out = df_out[flds_1 + flds_2]

    return df_out



def dict_to_excel(
    fp_out: str,
    dict_out: Dict[str, pd.DataFrame],
    replace_file: bool = False, 
) -> None:
    """
    Write a dictionary `dict_out` of dataframes to Excel file at path fp_out.
        Keys in dict_out are sheet names.

    Keyword Arguments
    -----------------
    - replace_file: if True, removes file if exists
    """

    (
        os.path.remove(fp_out)
        if os.path.exists(fp_out) & replace_file
        else None
    )

    with pd.ExcelWriter(fp_out) as excel_writer:
        for k in dict_out.keys():
            dict_out[k].to_excel(
                excel_writer, 
                sheet_name = str(k), 
                index = False, 
                encoding = "UTF-8"
            )



def div_with_modulo(
    n: int,
    d: int,
) -> Tuple[int, int]:
    """
    Divide numerator n by denominator d and return modulo if n > d
    """

    base = int(np.floor(n/d))
    modifier = int(n > d)*(n%d)

    return base, modifier



def do_array_mult(
    arr_stable: np.ndarray,
    arr_variable: np.ndarray,
    allow_outer: bool = True
) -> np.ndarray:
    """
    Multiply arrays while allowing for different shapes of arr_variable. Allows
        for multiplication of np.arrays that might be of the same shape or
        row-wise similar

    Function Arguments
    ------------------
    - arr_stable: array with base shape
    - arr_variable:
        * if arr_stable is 2d, arr_variable can have shapes
            arr_stable.shape or (arr_stable[1], )
        * if arr_stable is 1d, arr_variable can have shapes arr_stable.shape
            OR if allow_outer == True, returns
            `np.outer(arr_stable, arr_variable)`

    Keyword Arguments
    -----------------
    - allow_outer: if arrays are mismatched in shape, allow an outer product
        (returns np.outer(arr_stable, arr_variable))
    """
    if isinstance(arr_variable, float) or isinstance(arr_variable, int) or isinstance(arr_stable, float) or isinstance(arr_stable, int):
        return arr_variable*arr_stable
    elif (arr_variable.shape == arr_stable.shape):
        return arr_variable*arr_stable
    elif (len(arr_stable.shape) == 2):
        if (arr_variable.shape == (arr_stable.shape[1], )):
            return arr_variable*arr_stable
        elif arr_variable.shape == (arr_stable.shape[0], ):
            return (arr_stable.transpose()*arr_variable).transpose()
    elif allow_outer:
        return np.outer(arr_stable, arr_variable)
    else:
        raise ValueError(f"Error in do_array_mult: Incompatable shape {arr_variable.shape} in arr_variable. The stable array has shape {arr_stable.shape}.")



def explode_merge(
    df_x: pd.DataFrame,
    df_y: pd.DataFrame,
    field_dummy: str = "DUMMY_MERGE",
    sort_ordering: Union[List, None] = None,
    suffix_x: str = "_x",
    suffix_y: str = "_y"
) -> pd.DataFrame:
    """
    Explode two dataframes (direct product of data frame rows)

    Function Arguments
    ------------------
    - df_x: first data frame
    - df_y: second data frame

    Keyword Arguments
    -----------------
    - field_dummy: dummy field to use for temporary merge
    - sort_ordering: optional list of hierarchical fields to sort by. If None,
        no sorting is performed.
    """

    val_merge = 1

    ##  CHECK DATA FRAME FIELDS

    dict_rnm_x = {}
    dict_rnm_y = {}

    # check for dummy fields
    if field_dummy in df_x.columns:
        dict_rnm_x.update({field_dummy: f"{field_dummy}{suffix_x}"})
    if field_dummy in df_y.columns:
        dict_rnm_y.update({field_dummy: f"{field_dummy}{suffix_y}"})

    # check for shared fields
    fields_shared = list(set(df_x.columns) & set(df_y.columns))
    if len(fields_shared) > 0:
        dict_rnm_x = dict([(x, f"{x}{append_x}") for x in fields_shared])
        dict_rnm_y = dict([(x, f"{x}{append_y}") for x in fields_shared])


    ##  DO JOIN

    # copy and rename data frames to merge
    df_a = df_x.copy().rename(dict_rnm_x)
    df_a[field_dummy] = val_merge
    df_b = df_y.copy().rename(dict_rnm_y)
    df_b[field_dummy] = val_merge

    df_out = pd.merge(
        df_a,
        df_b,
        on = [field_dummy]
    ).drop([field_dummy], axis = 1)

    if isinstance(sort_ordering, list):
        sort_vals = [x for x in sort_ordering if x in df_out.columns]
        df_out.sort_values(by = sort_vals, inplace = True) if (len(sort_vals) > 0) else None

    df_out.reset_index(drop = True, inplace = True)

    return df_out



def fill_df_rows_from_df(
    df_target: pd.DataFrame,
    df_source: pd.DataFrame,
    fields_merge: list,
    fields_subset: list
) -> pd.DataFrame:
    """
    Fill missing rows in df_target with rows available in df_subset.

    Function Arguments
    ------------------
    - df_target: data frame containing NAs to be filled from df_source
    - df_source: data frame containing rows to use for filling NAs
    - fields_merge: fields in df_target and df_source to use for merging rows
        from df_source to df_target
    - fields_subset: fields in df_target to source from df_source
    """

    # check specifications
    set_fields_shared = set(df_target.columns) & set(df_source.columns)
    fields_merge = [x for x in fields_merge if x in set_fields_shared]
    fields_subset = [x for x in fields_subset if x in set_fields_shared]

    # split by NA/not NA; NA rows will get replaced
    filt_nas = df_target[fields_subset].isna().any(axis = 1)
    df_target_keep = df_target[~filt_nas]
    df_target_nas = df_target[filt_nas]

    if len(df_target_nas) > 0:
        # fields_diff are presumably the missing indices; merges fields_subset on fields_merge
        fields_diff = [x for x in df_target_nas.columns if (x not in fields_merge + fields_subset)]

        df_target_nas = pd.merge(
            df_target_nas[fields_diff + fields_merge],
            df_source[fields_merge + fields_subset],
            how = "left"
        )

        df_out = pd.concat(
            [df_target_keep, df_target_nas],
            axis = 0
        ).reset_index(drop = True)
    else:
        df_out = df_target_keep

    return df_out



def filter_data_frame_by_group(
    df_in: pd.DataFrame,
    fields_group: List[Any],
    field_value: str,
    val_exclude: float = 0.0
) -> pd.DataFrame:
    """
    Filter a data frame to remove all entries in a group have a single 
        value.
    
    Function Arguments
    ------------------
    - df_in: data frame to filter
    - fields_group: fields to use to set up groups
    - field_value: field to use as filtering value

    Keyword Arguments
    -----------------
    - val_exclude: exclude groups that are associated with *only* this value
        (generally zero)
    """
    # check fields
    fields_group = [x for x in fields_group if x in df_in.columns]

    stop_run = field_value not in df_in.columns
    stop_run = stop_run | (field_value in fields_group)
    stop_run = stop_run | (len(fields_group) == 0)

    if stop_run:
        return None


    # filter out unnecessary values
    df_filt = []
    val_exclude = float(val_exclude) if (isinstance(val_exclude, float) or isinstance(val_exclude, int)) else val_exclude
    df_grouped = df_in.groupby(
        fields_group
    )

    for df in df_grouped:
        tup, df = df
        col_vals = set([float(x) for x in list(df[field_value].unique())])
        df_filt.append(df) if ((len(col_vals) > 1) or not col_vals.issubset({val_exclude})) else None

    return_val = pd.concat(df_filt, axis = 0) if (len(df_filt) > 0) else df_in.iloc[0:0]

    return return_val



def filter_df_on_reference_df_rows(
    df_filter: pd.DataFrame,
    df_reference: pd.DataFrame,
    fields_index: List[str],
    fields_compare: List[str],
    fields_groupby: Union[List[str], None] = None,
    filter_method: str = "any",
    keep_comparison: bool = False
) -> pd.DataFrame:
    """
    Compare two data frames and drop rows from df_filter that are contained in
        df_reference. Merges on fields_index and filters based on
        fields_compare. In each row, values associated with fields_index in
        df_filter are compared to rows in df_reference with the same index rows.
        If the values are different, then the row is kep in df_filter. If the
        same, it is dropped.

    Function Arguments
    ------------------
    - df_filter: DataFrame to filter based on rows from df_reference
    - df_reference: DataFrame to use as a reference.
    - fields_index: fields in both to use for indexing
    - fields_compare: fields to use for comparison

    Keyword Arguments
    -----------------
    - fields_groupby: fields that group rows; if any (or all) rows differ within
        this group, the group will be kept. If they are all the same, the group
        will be dropped.
    - filter_method: "all" or "any"
        * Set to "any" to keep rows where *any* field contained in
            fields_compare is different.
        * Set to "any" to keep rows where *all* fields contained in
            fields_compare are different.
    - keep_comparison: keep fields used for comparison?
    """
    # check field specifications
    set_fields_both = set(df_filter.columns) & set(df_reference.columns)
    fields_index = [x for x in fields_index if x in set_fields_both]
    fields_compare = [x for x in fields_compare if x in set_fields_both]

    # special return cases
    if min(len(fields_index), len(fields_compare)) == 0:
        return None
    if not isinstance(df_filter, pd.DataFrame):
        return None
    if not isinstance(df_reference, pd.DataFrame):
        return df_filter


    ##  MERGE AND RENAME

    dict_rnm = dict([(x, f"{x}_compare") for x in fields_compare])
    dict_rnm_rev = reverse_dict(dict_rnm)
    fields_compare_ref = [dict_rnm.get(x) for x in fields_compare]

    df_compare = pd.merge(
        df_filter,
        df_reference[fields_index + fields_compare].rename(columns = dict_rnm),
        on = fields_index
    )

    fields_groupby = [x for x in fields_groupby if x in fields_index]
    fields_groupby = None if (len(fields_groupby) == 0) else fields_groupby

    if fields_groupby is None:
        df_check = (df_compare[fields_compare] != df_compare[fields_compare_ref].rename(columns = dict_rnm_rev))
        series_keep = df_check.any(axis = 1) if (filter_method == "any") else df_check.all(axis = 1)
        df_return = df_compare[series_keep][df_filter.columns].reset_index(drop = True)

    else:
        df_return = []
        df_group = df_compare.groupby(fields_groupby)

        for i in df_group:
            i, df = i

            df_check = (df[fields_compare] != df[fields_compare_ref].rename(columns = dict_rnm_rev))
            series_keep = df_check.any(axis = 1) if (filter_method == "any") else df_check.all(axis = 1)
            append_df = any(list(series_keep))

            df_return.append(df) if append_df else None

        df_return = pd.concat(df_return, axis = 0).reset_index(drop = True) if (len(df_return) > 0) else None

    if df_return is not None:
        df_return.drop(
            [x for x in df_return.columns if x in fields_compare_ref], 
            axis = 1,
            inplace = True
        ) if not keep_comparison else None

    return df_return



def filter_tuple(
    tup: Tuple,
    ignore_inds: Union[List[int], int]
) -> Tuple[Any]:
    """
    Filter a tuple to ignore indices at ignore_inds. Accepts a list of
        integers or a single integer.
    """
    ignore_inds = [ignore_inds] if isinstance(ignore_inds, int) else ignore_inds
    n = len(tup)
    return tuple(tup[x] for x in range(n) if (x not in ignore_inds))



def format_print_list(
    list_in: list,
    delim = ","
) -> str:
    """
    Print (as string) values of list_in to string separated by `delim`
    """
    str_return =  ((f"{delim} ").join(["'%s'" for x in range(len(list_in))]))%tuple(list_in)

    return str_return



def get_csv_subset(
    fp_table: Union[str, None],
    dict_subset: Union[Dict[str, List], None],
    fields_extract: Union[List[str], None] = None,
    chunk_size: int = 100000,
    max_iter: Union[int, None] = None,
    drop_duplicates: bool = True
) -> pd.DataFrame:
    """
    Return a subset of a CSV written in persistent storage without loading
        the entire file into memory (see PyTables for potential speed
        improvement).

    Function Arguments
    ------------------
    - fp_table: file path to CSV to read in
    - dict_subset: dictionary of fields to subset on, e.g.,

        dict_subset = {
            field_a = [v_a1, v_a2, ..., v_am)],
            field_b = [v_b1, v_b2, ..., v_bm)],
            .
            .
            .
        }

        * NOTE: only accepts discrete values

    Optional Arguments
    ------------------
    - fields_extract: fields to extract from the data frame.
        * If None, extracts all fields

    Keyword Arguments
    -----------------
    - fields_extract: fields to extract from the data frame.
    - chunk_size: get_csv_subset operates as an iterator, reading in
        chunks of data of length `chunk_size`. Larger values may be more
        efficient on machines with higher memory.
    - max_iter: optional specification of a maximum number of iterations.
        Only should be used for sampling data or when the structure of rows
        is known.
    - drop_duplicates: drop duplicates in table?
    """

    df_obj = pd.read_csv(
        fp_table,
        iterator = True,
        chunksize = chunk_size,
        engine = "c",
        usecols = fields_extract
    )

    df_out = []
    keep_going = True
    i = 0

    while keep_going:

        try:
            df_chunk = df_obj.get_chunk()
            df_chunk = subset_df(
                df_chunk,
                dict_subset
            )

            df_chunk.drop_duplicates(inplace = True) if drop_duplicates else None

        except Exception as e:
            keep_going = False
            break

        df_out.append(df_chunk) if (len(df_chunk) > 0) else None

        i += 1

        keep_going = False if (df_chunk is None) else keep_going
        keep_going = keep_going & (True if (max_iter is None) else (i < max_iter))

    df_out = pd.concat(df_out, axis = 0).reset_index(drop = True) if (len(df_out) > 0) else None

    return df_out



def get_cols_as_grouped_proportions(
    df_in: pd.DataFrame,
    fields_data: List[str],
    fields_group: List[str],
    drop_if_zero_sum: bool = False,
    include_other_fields: bool = True,
) -> Union[pd.DataFrame, None]:
    """
    Modify columns to be proportions based on a grouping of index fields. 
        Returns None if invalid fields are found. Otherwise, returns a DataFrame 
        with fields_data as proportions of the total within that column based on 
        grouping fields_group.
    
    Function Arguments
    ------------------
    - df_in: DataFrame with columns to calculate proportions for
    - fields_data: fields to calculate as proportions
    - fields_group: fields to group on
    
    Keyword Arguments
    -----------------
    - drop_if_zero_sum: if the sum of columns is zero, drop?
    - include_other_fields: include other data frame fields besides fields_data
        and fields_group?
    """
    # verify fields and return None if 
    fields_data = [x for x in fields_data if x in df_in.columns]
    fields_group = [x for x in fields_group if x in df_in.columns]
    if min(len(fields_data), len(fields_group)) == 0:
        return None
    
    # convert to monthly annual proportions 
    fields_incl = fields_group + fields_data
    fields_incl += [x for x in df_in.columns if x not in fields_incl] if include_other_fields else []
    df_grouped = df_in[fields_incl].groupby(fields_group)

    df_out = []
    for i, df in df_grouped:
        arr = np.array(df[fields_data]) 
        df[fields_data] = arr/arr.sum(axis = 0)
        (
            None
            if (np.max(arr.sum(axis = 0)) == 0) & drop_if_zero_sum 
            else df_out.append(df) 
        )
        
    df_out = pd.concat(df_out, axis = 0).reset_index(drop = True) 
    
    return df_out



def get_dict_from_lines(
    lines: List[str],
    splitter: Union[str, None] = None
) -> Union[Dict, None]:
    """
    Return a dictionary for use in converting an ascii input to arrays.
    
    Function Arguments
    ------------------
    - lines: list of input lines directly read from file (strings)
    
    Keyword Arguments
    -----------------
    - spltter: string to split on. If None, splits on whitespace
    """
    
    dict_out = {}
    
    for i, line in enumerate(lines):
        
        tup = line.strip().split(splitter)
        key, val = (tup[0], tup[1]) if (len(tup) == 2) else (tup, None)

        key = str(key)
        val = tryparse_str_to_num(val)
        

        dict_out.update({key: val})
        
    return dict_out



def get_dimensional_values(
    keys_in: Union[List[str], str],
    key: str,
    delim: str = ",",
    return_type: type = int,
) -> List[int]:
    """
    Read in dimensional values from a string OR a csv file. `keys_in` can be a list of values separated by
        `delim`, or a path to a text file--the text file will be read as a data
        frame and must contain column header key.
    
    Function Arguments
    ------------------
    - keys_in: 
        * if not os.path.exists(keys_in): list of values separated by `delim`
        * if os.path.exists(keys_in): tries to read as a csv, pulling from
             column `key`
    - key: optional column specification

    Keyword Arguments
    -----------------
    - delim: delimitter to use for input strings
    - return_type: type to convert output to
    """

    values = None

    # if list, return values
    if islistlike(keys_in):
        try:
            values = [return_type(x) for x in keys_in]
        except Exception as e:
            raise RuntimeError(f"Error converting elements to integer in get_dimensional_values(): {e}")
        return values
    
    # if passing an integer, return integer in a list
    if isinstance(keys_in, return_type) & (return_type != str):
        return [keys_in]

    # otherwise, return none
    if not isinstance(keys_in, str):
        return None


    ##  GET VALUES FROM STRING

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



def get_index_fields_count(
    df_in: pd.DataFrame,
    field_count: str = "count",
    field_frac: str = "frac",
    fields_index: Union[List[str], None] = None,
) -> pd.DataFrame:
    """
    Function Arguments
    ------------------
    - df_in: DataFrame containing data to get count by
    
    Keyword Arguments
    -----------------
    - field_count: field storing number of rows associated with the 
        grouping
    - field_frac: add fraction?
    - fields_index: optional specification of fields to group by. If None, 
        uses all fields in input data
    """
    fields_index = (
        list(df_in.columns)
        if not islistlike(fields_index)
        else [x for x in fields_index if x in df_in.columns]
    )
    if len(fields_index) == 0:
        return None
    
    df_out = df_in[fields_index].copy()
    df_out[field_count] = 1
    
    df_out = simple_df_agg(
        df_out,
        fields_index,
        {
            field_count: "sum"
        },
    )
    
    return df_out



def get_repeating_vec_element_inds(
    inds: Union[list, np.ndarray],
    n_elements: int,
    n_repetitions_inner: Union[int, None],
    n_repetitions_outer: Union[int, None]
) -> np.ndarray:
    """
    Get indices for elements specified from an input indexing vector, which
        indexes a vector that has been repeated an inner number of times
        (within the cycle) and an outer number of times (number of times to
        cycle).

    Function Arguments
    ------------------
    - inds: indices to extract from an np.ndarray of values that is repeated
        using build_repeating_vec.
    - n_elements: number of elements contained in the original array
    - n_repetitions_inner: number of inner repetitions. E.g., for a vector
        vec = [0, 1, 2], if n_repetitions_inner = 3, then the inner component
        (the component that is repeated an outer # of times) would be

        vec_inner = [0, 0, 0, 1, 1, 1, 2, 2, 2]

    - n_repetitions_outer: number of outer repetitions. E.g., for vec_inner from
        above, if n_repetitions_outer = 3, then the final output component would
        be

        vec = [0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 0, 0, 1, 1, 1, 2, 2, 2]
    """
    try:
        inds = np.array([x for x in inds if x < n_elements])
    except Exception as e:
        raise RuntimeException(f"Error trying to set inds in get_repeating_vec_element_inds(): {e}")
    inds = inds if (len(inds.shape) == 1) else inds.flatten()

    # generate indices for the desired elements in the inner vector
    inds_inner = (
        np.repeat([inds], n_repetitions_inner, axis = 0
    ).transpose()*n_repetitions_inner + np.arange(n_repetitions_inner)).flatten()

    # get length of inner "potential" space
    n_inner = n_repetitions_inner*n_elements

    # expand and generate indices for desired elements
    inds_ext = (
        np.repeat([inds_inner], n_repetitions_outer, axis = 0).transpose() + np.arange(n_repetitions_outer)*n_inner
    ).transpose().flatten()

    return inds_ext



def get_time_elapsed(
    t_0: float,
    n_digits: int = 2
) -> str:
    """
    Get the time elapsed from reference point t_0. Use `n_digits` to specify 
        rounding.
    """
    t_elapsed = np.round(time.time() - t_0, n_digits)

    return t_elapsed



def get_vector_growth_rates_from_first_element(
    arr: np.ndarray
) -> np.ndarray:
    """
    Using a 1- or 2-dimentionsal Numpy array, get growth scalars (columnar) 
        relative to the first element

    Function Arguments
    ------------------
    - arr: input array to use to derive growth rates
    """
    arr = np.nan_to_num(arr[1:]/arr[0:-1], 0.0, posinf = 0.0)
    elem_concat = np.ones((1, )) if (len(arr.shape) == 1) else np.ones((1, arr.shape[1]))
    arr = np.concatenate([elem_concat, arr], axis = 0)
    arr = np.cumprod(arr, axis = 0)

    return arr



def group_df_as_dict(
    df_in: pd.DataFrame,
    fields_group: List[str],
    fields_out_set: Union[List[str], str, None] = None
) -> Union[Dict[Tuple, pd.DataFrame], None]:
    """
    Group a data frame df_in by fields group and return a dictionary of unique 
        fields_group -> applicable rows in the DataFrame.
        
    Returns None if fields_group is not specified properly (including specifying 
        no fields)

    Function Arguments
    ------------------
    - df_in: input data frame to use
    - fields_group: fields to group on for generating the dictionary

    Keyword Arguments
    -----------------
    - fields_out_set: If not None, then will extract unique elements in these 
        fields (if a list, as a data frame of unique rows; if a single element,
        then as a set)
    """
    
    fields_group = [x for x in fields_group if x in df_in.columns]
    if len(fields_group) == 0:
        return None
    
    df_in_grouped = df_in.groupby(fields_group)
    dict_out = {}

    for i, df in df_in_grouped:
        
        val = df

        if fields_out_set is not None:
            val = (
                val[fields_out_set].drop_duplicates()
                if isinstance(fields_out_set, list)
                else sorted(list(set(list(val[fields_out_set]))))
            )

        dict_out.update({i: val})
        
    return dict_out



def islistlike(
    x: Any
) -> bool:
    """
    Check if x is a list, np.array, or range
    """
    types_check = (list, np.ndarray, range)
    out = isinstance(x, types_check)

    return out



def isnumber(
    x: Any,
    integer: bool = False
) -> bool:
    """
    Check if x is an integer or float. Set integer = True to force integer only
        checks.
    """
    types_check = (
        (int, float, np.int64, np.int32, np.int, np.float64, np.float32, np.float)
        if not integer
        else (int, np.int64, np.int32, np.int)
    )
    out = isinstance(x, types_check)

    return out



def list_dict_keys_with_same_values(self,
    dict_in: dict,
    delim: str = "; "
) -> str:
    """
    Scan `dict_in` for keys associated with repeat values. Returns ""
    if no two keys are associated with the same values.
    """
    combs = itertools.combinations(list(dict_in.keys()), 2)
    str_out = []
    for comb in combs:
        comb_0 = dict_in.get(comb[0])
        comb_1 = dict_in.get(comb[1])
        if comb_0 == comb_1:
            comb_out = f"'{comb_0}'" if isinstance(comb_0, str) else comb_0
            str_out.append(f"{comb[0]} and {comb[1]} (both = {comb_out})")
    str_out = delim.join(str_out) if (len(str_out) > 0) else ""

    return str_out



def match_df_to_target_df(
    df_target: pd.DataFrame,
    df_source: pd.DataFrame,
    fields_index: list,
    fields_to_replace: str = None,
    fillna_value: Union[int, float, str] = 0.0,
    overwrite_only: bool = True
) -> pd.DataFrame:
    """
    Merge df_source to df_target, overwriting data fields in df_target with 
        those in df_source

    Function Arguments
    ------------------
    - df_target: target data frame, which will have values replaced with values 
        in df_source
    - df_source: source data to use to replace
    - fields_index: list of index fields

    Keyword Arguments
    -----------------
    - fields_to_replace: fields to replace in merge. If None, defaults to all 
        available.
    - fillna_value: value to use to fill nas in data frame
    - overwrite_only: only overwrite columns in df_target with those in 
        df_source. If False, will merge in fields that are not in df_target.
    """

    # get some fields
    check_fields(df_target, fields_index)
    check_fields(df_source, fields_index)

    if not isinstance(df_source, pd.DataFrame):
        return df_target

    # get fields to replace
    fields_dat_source = [x for x in df_source.columns if (x not in fields_index)]
    fields_dat_source = (
        [x for x in fields_dat_source if (x in df_target.columns)] 
        if overwrite_only 
        else fields_dat_source
    )
    fields_dat_source = (
        [x for x in fields_dat_source if x in fields_to_replace] 
        if (fields_to_replace is not None) 
        else fields_dat_source
    )

    # target fields to drop
    fields_dat_target = [x for x in df_target.columns if (x not in fields_index)]
    fields_dat_target_drop = [x for x in fields_dat_target if (x in fields_dat_source)]
    
    # make a copy and rename
    df_out = pd.merge(
        df_target.drop(fields_dat_target_drop, axis = 1),
        df_source[fields_index + fields_dat_source],
        how = "left",
        on = fields_index
    )
    
    df_out.fillna(fillna_value, inplace = True)
    df_out = (
        df_out[df_target.columns].reset_index(drop = True)
        if overwrite_only
        else df_out.reset_index(drop = True)
    )

    return df_out



def mean_median_ratio(
    vec: np.ndarray,
) -> np.ndarray:
    """
    Get a function for checking a measure of skew; used in checking output
    """
    
    mu = vec.mean()
    med = np.median(vec)
    
    if med == 0:
        v = vec[vec != 0]
        mu = v.mean() if (len(v) > 0) else 0.0
        med = np.median(v) if (len(v) > 0) else 1.0
    
    out = (mu/med) if (med != 0) else 0.0
    
    return out



def merge_output_df_list(
    dfs_output_data: list,
    model_attributes,
    merge_type: str = "concatenate",
    additional_dimensions: Union[List[str], None] = None,
) -> pd.DataFrame:
    """
    Merge data frames together into a single output when they share ordered 
        dimensions of analysis (from ModelAttribute class)

    Function Arguments
    ------------------
    - dfs_output_data: list of data frames to join
    - model_attributes: model_attributes.ModelAttributes object (NOT referenced 
        here to avoid loading package, which would create circular logic)
    
    Keyword Arguments
    -----------------
    - additional_dimensions: optional specification of additional dimensions to 
        join on
    - merge_type: "concatenate" or "merge". "merge" is slower but may be 
        necessary if row indices are not the same across 
    """
    # check type
    valid_merge_types = ["concatenate", "merge"]
    if merge_type not in valid_merge_types:
        str_valid_types = format_print_list(valid_merge_types)
        raise ValueError(f"Invalid merge_type '{merge_type}': valid types are {str_valid_types}.")

    # start building the output dataframe and retrieve dimensions of analysis for merging/ordering
    dfs_output_data = [x for x in dfs_output_data if (x is not None)]
    df_out = dfs_output_data[0].copy()
    dims_to_order = model_attributes.sort_ordered_dimensions_of_analysis.copy()
    dims_to_order += (
        sorted(list(set(additional_dimensions)))
        if islistlike(additional_dimensions)
        else []
    )
    dims_in_out = set([x for x in dims_to_order if x in df_out.columns])

    # some basic returns
    if (len(dfs_output_data) == 0):
        return None

    if len(dfs_output_data) == 1:
        return dfs_output_data[0]

 
    # loop to merge where applicable
    for i in range(1, len(dfs_output_data)):
        if merge_type == "concatenate":
            # check available dims; if there are ones that aren't already contained, keep them. Otherwise, drop
            fields_dat = [x for x in dfs_output_data[i].columns if (x not in dims_to_order)]
            fields_new_dims = [
                x for x in dfs_output_data[i].columns 
                if (x in dims_to_order) 
                and (x not in dims_in_out)
            ]
            dims_in_out = dims_in_out | set(fields_new_dims)
            dfs_output_data[i] = dfs_output_data[i][fields_new_dims + fields_dat]

        elif merge_type == "merge":
            df_out = pd.merge(df_out, dfs_output_data[i])


    # clean up - assume merged may need to be re-sorted on rows
    if merge_type == "concatenate":
        fields_dim = [x for x in dims_to_order if x in dims_in_out]
        df_out = pd.concat(dfs_output_data, axis = 1).reset_index(drop = True)

    elif merge_type == "merge":
        fields_dim = [x for x in dims_to_order if x in df_out.columns]
        df_out = (
            pd.concat(df_out, axis = 1)
            .sort_values(by = fields_dim)
            .reset_index(drop = True)
        )

    fields_dat = sorted([x for x in df_out.columns if x not in dims_in_out])

    return df_out[fields_dim + fields_dat]



def _optional_log(
    logger: Union[logging.Logger, None],
    msg: str,
    type_log: str = "log",
    warn_if_none: bool = True,
    **kwargs
):
    """
    Log using logging.Logger if an object is defined; Otherwise, no action.

    Function Arguments
    ------------------
    - logger: logging.Logger object used to log events. If None, no action is
        taken
    - msg: msg to pass in log

    Keyword Arguments
    -----------------
    - type_log: type of log to execute. Acceptable values are:
        * "critical": logger.critical(msg)
        * "debug": logger.debug(msg)
        * "error": logger.error(msg)
        * "info": logger.info(msg)
        * "log": logger.log(msg)
        * "warning": logger.warning(msg)
    - warn_if_none: pass a message through warnings.warn() if logger is None
    - **kwargs: passed as logger.METHOD(msg, **kwargs)

    See https://docs.python.org/3/library/logging.html for more information on
        Logger methods and calls
    """
    if isinstance(logger, logging.Logger):

        valid_type_log = [
            "critical",
            "debug",
            "error",
            "info",
            "log",
            "warning"
        ]

        if type_log not in valid_type_log:
            warnings.warn(f"Warning in optional_log: log type '{type_log}' not found. Defaulting to type 'log'.")
            type_log = "log"

        if type_log == "critical":
            logger.critical(msg, **kwargs)
        elif type_log == "debug":
            logger.debug(msg, **kwargs)
        elif type_log == "error":
            logger.error(msg, **kwargs)
        elif type_log == "info":
            logger.info(msg, **kwargs)
        elif type_log == "warning":
            logger.warning(msg, **kwargs)
        else:
            logger.log(msg, **kwargs)

    elif warn_if_none:
        warnings.warn(f"Warning passed from optional_log: {msg}.")



def orient_df_by_reference_vector(
    df_in: pd.DataFrame,
    vector_reference: Union[list, np.ndarray],
    field_compare: str,
    field_merge_tmp: str = "ID_SORT_",
    drop_field_compare: bool = False
) -> pd.DataFrame:
    """
    Ensure that data frame field `field_compare` is ordered properly (in the 
        same ordering as `vector_reference`). Returns a data frame with the 
        correct row ordering.

    Function Arguments
    ------------------
    - df_in: data frame to check
    - vector_reference: reference vector used to order df_in[field_compare].
    - field_compare: field to order df_in by

    Keyword Arguments
    -----------------
    - field_merge_tmp: temporary field to use for sorting. Should not be in
        df_in.columns
    - drop_field_compare: drop the comparison field after orienting

    Note
    ----
    * Should only be used if field_compare is the only field in df_in to be
        sorted on. Additional sorting is not supported.
    """

    # check reference
    if (list(df_in[field_compare]) == list(vector_reference)):
        df_out = df_in
    else:
        df_tmp = pd.DataFrame({field_merge_tmp: range(len(vector_reference)), field_compare: vector_reference})
        df_out = pd.merge(df_out, df_tmp).sort_values(by = [field_merge_tmp]).reset_index(drop = True)
        df_out = df_out[df_in.columns]

    # drop the sort field if needed
    df_out.drop([field_compare], axis = 1, inplace = True) if drop_field_compare else None

    return df_out



def pivot_df_clean(
    df_pivot: pd.DataFrame,
    fields_column: List[str],
    fields_value: List[str]
) -> pd.DataFrame:
    """
    Perform a pivot that resets indices and names columns. Assumes all
        fields not pass as column or value are indices.

    Function Arguments
    ------------------
    - df_pivot: DataFrame to pivot
    - fields_column: fields to pass to pd.pivot() as `columns`
    - fields_value: fields to pass to pd.pivot() as `value`
    """
    # check fields
    fields_column = [x for x in fields_column if x in df_pivot.columns]
    fields_value = [x for x in fields_value if x in df_pivot.columns]
    fields_ind = [x for x in df_pivot.columns if x not in fields_column + fields_value]
    # return if empty
    if min([len(x) for x in [fields_column, fields_ind, fields_value]]) == 0:
        return None

    # pivot and clean indices
    df_piv = pd.pivot(
        df_pivot,
        fields_ind,
        fields_column,
        fields_value
    ).reset_index()

    df_piv.columns = [
        x[0] if (x[1] == "") else x[1] for x in df_piv.columns.to_flat_index()
    ]

    return df_piv



def print_setdiff(
    set_required: set,
    set_check: set
) -> str:
    """
    Print a set difference; sorts to ensure easy reading for user.
    """
    missing_vals = sorted(list(set_required - set_check))
    return format_print_list(missing_vals)



def project_from_array(
    arr_in: np.ndarray,
    max_deviation_from_mean: float = 0.2
) -> np.ndarray:
    """
    Use a regression to project next value + apply bounds to maximum 
        deviation from the observed mean. Useful for projecting a sequential
        observation in a time series.
        
    Function Arguments
    ------------------
    - arr_in: 2-d array with rows representing observations (or time) and
        columns representing different variables. 
    
    Keyword Arguments
    -----------------
    - max_deviation_from_mean: maximium proportional deviation from mean; used
        to prevent large swings in the regression.
    """
    
    n, m = arr_in.shape
    x = np.array([range(n), np.ones(n)]).transpose()
    xtx_inv = np.linalg.inv(np.dot(x.transpose(), x))
    
    vec_inputs_proj = np.array([[n + 1 , 1]])
    vec_output_proj_by_class = np.zeros(m)
                               
    for i in range(m):       
                               
        y = np.array([arr_in[:, i]]).transpose()
        y_bar = np.mean(y)
        bounds = ((1 - max_deviation_from_mean)*y_bar, (1 + max_deviation_from_mean)*y_bar)
        
        xty = np.dot(x.transpose(), y)
        coeffs = np.dot(xtx_inv, xty)

        # revert to mean if any issues with NaNs show up (incl singularity)
        val = np.dot(vec_inputs_proj, coeffs)[0, 0]
        val = y_bar if np.isnan(val) else val
        
        vec_output_proj_by_class[i] = float(vec_bounds(val, bounds))
        
    return vec_output_proj_by_class



def project_growth_scalar_from_elasticity(
    vec_rates: np.ndarray,
    vec_elasticity: np.ndarray,
    rates_are_factors = False,
    elasticity_type = "standard"
):
    """
    Project a vector of growth scalars from a vector of growth rates and
        elasticities

    Function Arguments
    ------------------
    - vec_rates: a vector of growth rates, where the ith entry is the growth
        rate of the driver from i to i + 1. If rates_are_factors = False
        (default), rates are proportions (e.g., 0.02). If
        rates_are_factors = True, then rates are scalars (e.g., 1.02)
    - vec_elasticity: a vector of elasticities.

    Keyword Arguments
    -----------------
    - rates_are_factors: Default = False. If True, rates are treated as
        growth factors (e.g., a 2% growth rate is entered as 1.02). If
        False, rates are growth rates (e.g., 2% growth rate is 0.02).
    - elasticity_type: Default = "standard"; acceptable options are
        "standard" or "log"
        * If standard, the growth in the demand is 1 + r*e, where r = is
            the growth rate of the driver and e is the elasiticity.
        * If log, the growth in the demand is (1 + r)^e
    """
    # CHEKCS
    if vec_rates.shape[0] + 1 != vec_elasticity.shape[0]:
        raise ValueError(f"Invalid vector lengths of vec_rates ('{len(vec_rates)}') and vec_elasticity ('{len(vec_elasticity)}'). Length of vec_elasticity should be equal to the length vec_rates + 1.")
    
    valid_types = ["standard", "log"]
    if elasticity_type not in valid_types:
        v_types = format_print_list(valid_types)
        raise ValueError(f"Invalid elasticity_type {elasticity_type}: valid options are {v_types}.")
    
    # check factors
    if rates_are_factors:
        vec_rates = vec_rates - 1 if (elasticity_type == "standard") else vec_rates
    else:
        vec_rates = vec_rates if (elasticity_type == "standard") else vec_rates + 1

    # check if transpose needs to be used
    transpose_q = (len(vec_rates.shape) != len(vec_elasticity.shape))

    # get scalar
    if elasticity_type == "standard":

        rates_adj = (vec_rates.transpose()*vec_elasticity[0:-1].transpose()).transpose() if transpose_q else vec_rates*vec_elasticity[0:-1]
        vec_growth_scalar = np.cumprod(1 + rates_adj, axis = 0)
        ones = np.ones(1) if (len(vec_growth_scalar.shape) == 1) else np.ones((1, vec_growth_scalar.shape[1]))
        vec_growth_scalar = np.concatenate([ones, vec_growth_scalar])

    elif elasticity_type == "log":

        ones = np.ones(1) if (len(vec_rates.shape) == 1) else np.ones((1, vec_rates.shape[1]))
        vec_growth_scalar = np.cumprod(np.concatenate([ones, vec_rates], axis = 0)**vec_elasticity)

    return vec_growth_scalar



def prepend_first_element(
    array: np.ndarray, 
    n_rows: int
) -> np.ndarray:
    """
    Repeat the first row of array `n_rows` times and prepend
    """
    out = np.concatenate([
        np.repeat(array[0:1], n_rows, axis = 0), array
    ])

    return out



def ramp_generic(
    x: Union[float, int], 
    n: int, 
    a: int, 
    b: int, 
    c: Union[float, int],
    d: Union[float, int, None] = None,
) -> float:
    """
    *defaults*

    for linear:
    set a = 0, b = 2, c = 1, d = n/2
    for sigmoid:
    set a = 1, b = 0, c = math.e, d = n/2
    """

    d = n/2 if (d is None) else d
    out = (a*n + b*x)/(n*(1 + c**(d - x)))

    return out



def read_array_from_file(
    fp: str,
    n_cols: int,
    min_ind: int,
    max_ind: int,
    delim: str = ",",
    skip_header: bool = True,
) -> np.ndarray:
    """
    Read an array from a file. min_ind is first row, max_ind is last row + 1
        (python style indexing). Only works with numeric values.
        
    Reads like data frame index, so 0 would be the first row of data (unless
        skip_header = False)
        
    Keyword Arguments
    -----------------
    - delim: data deliminter
    - skip_header: skip the first row
    """
    
    skiprows = min_ind
    skiprows += 1 if skip_header else 0

    n_rows = max_ind - min_ind + 1
    arr_out = np.ones((n_rows, n_cols)).astype(float)
    
    with open(fp, "r") as fl:
        for i in range(skiprows):
            next(fl)
            
        for i in range(n_rows):
            row = fl.readline().strip().split(delim)
            arr_out[i] = np.array([float(x) for x in row])
            
    return arr_out
        


def read_ascii(
    fp: str
) -> Union[np.ndarray, None]:
    """
    Read a geo ascii table for storage from file fp
    """
    n_header = 6
    
    if not os.path.exists(fp):
        return None
    
    # get information dictionary
    with open(fp, "r") as file_ascii:
        lines = []
        for i in range(n_header):
            lines.append(file_ascii.readline())
    dict_info = get_dict_from_lines(lines)
    
    # get the data array
    arr = np.loadtxt(fp, skiprows = n_header)
    
    return dict_info, arr



def read_text(
    fp: str,
    as_lines: bool = True,
) -> Union[str, None]:
    """
    Read text file from path fp. Set as_lines = False to read as
        a single text stream.
    """
    return_none = not isinstance(fp, str)
    return_none |= (
        not os.path.exists(fp)
        if not return_none
        else False
    )
    if return_none:
        return None
    
    with open(fp, "r") as fl:
        lines = (
            fl.readlines()
            if as_lines
            else fl.read()
        )
        
    return lines



def read_yaml(
    fp: str,
    munchify_dict: bool = True,
) -> Union[Dict, munch.Munch, None]:
    """
    Read a yaml file 
    
    Function Arguments
    ------------------
    - fp: path to yaml to read
    
    Keyword Arguments
    -----------------
    - munchify_dict: convert to Munch object (nested class dictionaries)
    """

    return_none = not isinstance(fp, str)
    return_none |= (
        not os.path.exists(fp)
        if not return_none
        else False
    )

    if return_none:
        return None

    with open(fp, "r") as fl:
        out = yaml.safe_load(fl)
    
    out = munch.munchify(out) if munchify_dict else out
    
    return out



def repl_array_val_twodim(
    array: np.ndarray, 
    val_repl: Any, 
    val_new: Any
) -> None:
    """
    Replace values in a two-dimensional array
    """

    w = np.where(array == val_repl)
    inds = w[0]*len(array[0]) + w[1]
    np.put(array, inds, val_new)

    return None



def replace_numerical_column_from_merge(
    df_target: pd.DataFrame,
    df_source: pd.DataFrame,
    field_to_replace: str,
    field_temporary: str = "NEWFIELDTMP"
):
    """
    Replace values in field_to_replace in df_source associated with values in
        df_replacement and shared index fields

    Function Arguments
    ------------------
    - df_target: target data frame, which will have values replaced with values
        in df_source
    - df_source: source data to use to replace
    - field_to_replace: field to replace in merge

    Keyword Arguments
    -----------------
    - field_temporary: temporary field used in reassignment

    Notes
    -----
    * all fields in df_source must be contained in df_target. Only works for
        numerical methods at the moment.
    """
    check_fields(df_target, list(df_source.columns))
    check_fields(df_source, [field_to_replace])

    # merge in
    fields_merge = list((set(df_target.columns) & set(df_source.columns)) - set([field_to_replace]))
    df_source_new = df_source.copy().rename(columns = {field_to_replace: field_temporary})
    df_out = df_target.copy()
    df_out = pd.merge(df_out, df_source_new, on = fields_merge, how = "left")

    # find rows where there are new values
    w = np.where(~np.isnan(np.array(df_out[field_temporary])))[0]
    df_out[field_temporary].fillna(0.0, inplace = True)

    if len(w) > 0:
        df_out.loc[w, field_to_replace] = 0.0
        df_out[field_to_replace] = np.array(df_out[field_to_replace]) + np.array(df_out[field_temporary])
    # drop temporary field, sort by index
    df_out = df_out[df_target.columns].sort_index()

    return df_out



def reverse_dict(
    dict_in: dict,
    allow_multi_keys: bool = False,
    force_list_values: bool = False,
) -> dict:
    """
    Reverse a dictionary, mapping v -> k for a dictionary of key value pairs 
        {k: v}

    Function Arguments
    ------------------
    - dict_in: dictionary to reverse

    Keyword Arguments
    -----------------
    - allow_multi_keys: if True, will map a non-injective dictionary 

        {
            k1: v0,
            k2: v0,
            k3: v3,
            ...
        }

            to 

        {
            v0: [k1, k2],
            v3: [k3]
        }

        * Note: all keys in the reverse dict will be lists. 
    - force_list_values: forces dictionary values to be a list. Useful if using
        with allow_multi_keys = True to ensure that dictionary values are always
        a list.
    """
    # check keys
    s_vals = set(dict_in.values())
    s_keys = set(dict_in.keys())
    dict_out = None

    if len(s_vals) != len(s_keys):
        if not allow_multi_keys:
            raise KeyError(f"Invalid dicionary in reverse_dict: the dictionary is not injective.")
        else:
            dict_out = {}
            for v in list(s_vals):
                ks = [k for k in dict_in.keys() if (dict_in.get(k) == v)]
                dict_out.update({v: ks})
    else:
        dict_out = (
            dict((v, k) for k, v in dict_in.items())
            if not force_list_values
            else dict((v, [k]) for k, v in dict_in.items())
        )

    return dict_out



def scalar_bounds(
    scalar: Union[float, int],
    bounds: tuple
) -> Union[float, int]:
    """
    set a scalar to stay within bounds
    """
    bounds = np.array(bounds).astype(float)
    val_out = min([max([scalar, min(bounds)]), max(bounds)])

    return val_out



def simple_df_agg(
    df_in: pd.DataFrame,
    fields_group: list,
    dict_agg: Dict[str, str],
    group_fields_ordered_for_sort_q: bool = False,
) -> pd.DataFrame:
    """
    Take an input dataframe, set grouping fields, and assume all other fields 
        are data (see `fields_agg` keyword argument for specifying other 
        fields). Then, apply the same 'agg_func' to data fields.

    Function Arguments
    ------------------
    - df_in: input data frame to aggregate over
    - fields_group: fields to group the data frame by
    - dict_agg: dictionary mapping field to aggregation function; data fields to
        aggregate are keys

    Keyword Arguments
    -----------------
    - group_fields_ordered_for_sort_q: bool. Default = False. If True, the 
        grouping fields are ordered and used to sort the output dataframe after 
        aggregation.
    """
    
    # check input fields and keys
    proceed_q = check_fields(df_in, fields_group, throw_error_q = False)
    if not proceed_q:
        return df_in

    # initialize output data frame, check specifications, and aggregate if checks are passed
    df_out = df_in.copy()
    if (isinstance(fields_group, list) and isinstance(dict_agg, dict)):
        fields_group = [x for x in fields_group if x in df_out.columns]
        dict_agg = dict((k, v) for k, v in dict_agg.items() if (k in df_out.columns) and (k not in fields_group))

        if (len(fields_group) > 0) & (len(dict_agg) > 0):
            dict_agg.update(dict((x, "first") for x in fields_group))

            df_out = df_out[list(dict_agg.keys())]
            df_out = df_out.groupby(fields_group).agg(dict_agg).reset_index(drop = True)
            df_out = df_out.sort_values(by = fields_group) if (group_fields_ordered_for_sort_q) else df_out

    return df_out



def sort_integer_strings(
	vector: List[str],
	regex_int: re.Pattern = re.compile("(\d*$)")
) -> List[str]:
	"""
	Sort the list `vector` of strings with respect to integer ordering.
	"""

	vector_int = sorted([int(x) for x in vector if regex_int.match(x) is not None])
	vector_non_int = [x for x in vector if regex_int.match(x) is None]

	vector_out = sorted(vector_non_int)
	vector_out += [str(x) for x in vector_int]

	return vector_out



##  
def str_replace(
    str_in: str,
    dict_replace: dict
) -> str:
    """
    Multiple string replacements using a dictionary. Operates in order
        NOTE: Should be modified to use OrderedDict
    """

    for k in dict_replace.keys():
        str_in = str_in.replace(k, dict_replace[k])
    return str_in



def str_split(
    x: str, 
    delim: str = ",",
    return_type: type = str,
):
    """
    Split string x using delimiter delim. Tries to return return_type. Useful
        for applying to DataFrames.
    """
    out = x.split(delim)
    try:
        out = [return_type(y) for y in out]
    except Exception as e:
        None

    return out



def subset_df(
    df: pd.DataFrame,
    dict_in: Union[Dict[str, List], None]
) -> pd.DataFrame:
    """
    Function Arguments
    ------------------
    - df: data frame to reduce
    = dict_in: dictionary used to reduce df that takes the following form:

        dict_in = {
            field_a = [v_a1, v_a2, v_a3, ... v_an],
            field_b = v_b,
            .
            .
            .
        }

        where `field_a` and `field_b` are fields in the data frame and

            [v_a1, v_a2, v_a3, ... v_an]

        is a list of acceptable values to filter on, and

            v_b

        is a single acceptable value for field_b.

    """


    dict_in = {} if not isinstance(dict_in, dict) else dict_in

    for k in dict_in.keys():
        if k in df.columns:
            val = [dict_in.get(k)] if not isinstance(dict_in.get(k), list) else dict_in.get(k)
            df = df[df[k].isin(val)]

    df.reset_index(drop = True, inplace = True)

    return df



def tryparse_str_to_num(
    val: Union[str, float, int, None],
    return_integer_if_round: bool = True
) -> Union[str, float, int, None]:
    """
    Try to convert val to float or integer
    
    NOTE: isnumeric() is insufficient, as it is unable to accurately
        identify scientific numbers. Additionally, it does not allow
        for conversion to integers automatically. 
        
    Function Arguments
    ------------------
    - val: value to attempt to convert
    
    Keyword Arguments
    ------------------
    - return_integer_if_round: if value is numeric, convert to integer
        if is integer equivalent?
    """
    
    if val is None:
        return None
    
    val = str(val)
    
    try: 
        val = float(val)
    except:
        val = str(val)
    
    val = (
        (int(val) if ((val == round(val)) & return_integer_if_round) else val)
        if isinstance(val, float)
        else val
    )
    
    return val



def vec_bounds(
    vec: Union[list, np.ndarray],
    bounds: Union[Tuple[float, float], None],
    cycle_vector_bounds_q: bool = False,
) -> Union[list, np.ndarray]:
    """
    Bound a vector vec within a range set within 'bounds'.

    Function Arguments
    ------------------
    - vec: list or np.ndarray of values to bound
    - bounds: tuple (single bound) or list vec specifying element-wise bounds. 
        NOTE: only works if

        vec.shape = (len(vec), ) == (len(bounds), )

    Keyword Arguments
    -----------------
    - cycle_vector_bounds_q: cycle bounds if there is a mismatch and the bounds 
        are entered as a vector
    """
    # check bounds
    if (bounds is None) or (vec is None):
        return vec

    # initialize bools -- using paried vector + is there a vector of bounds?
    paired_vector_check = False # later depends on use_bounding_vec
    use_bounding_vec = False

    # check if specification is a list of tuples
    if len(np.array(bounds).shape) > 1:

        # initialize error check
        if isinstance(bounds[0], np.ndarray) and isinstance(bounds[1], np.ndarray) and isinstance(vec, np.ndarray):
            paired_vector_check = (bounds[0].shape == bounds[1].shape) and (bounds[0].shape == vec.shape)
            if paired_vector_check:
                shape_reset = vec.shape
                bounds = [tuple(x) for x in zip(bounds[0].flatten(), bounds[1].flatten())]
                vec = vec.flatten()

        tuple_entry_check = all(isinstance(x, tuple) for x in bounds)
        error_q = not tuple_entry_check

        # restrict use_bounding_vec to vector vs. vector with dim (n, )
        dim_vec = (len(vec), ) if isinstance(vec, list) else vec.shape
        error_q = error_q or (len(dim_vec) != 1)

        # check element types
        if len(bounds) == len(vec):
            use_bounding_vec = True
        elif cycle_vector_bounds_q:
            use_bounding_vec = True
            n_b = len(bounds)
            n_v = len(vec)
            bounds = bounds[0:n_v] if (n_b > n_v) else sum([bounds for x in range(int(np.ceil(n_v/n_b)))], [])[0:n_v]
        elif not error_q:
            bounds = bounds[0]
            use_bounding_vec = False
        #
        if error_q:
            raise ValueError(f"Invalid bounds specified in vec_bounds:\n\t- Bounds should be a tuple or a vector of tuples.\n\t- If the bounding vector does not match length of the input vector, set cycle_vector_bounds_q = True to force cycling.")

    if not use_bounding_vec:
        def f(x):
            return scalar_bounds(x, bounds)
        f_z = np.vectorize(f)
        vec_out = f_z(vec).astype(float)
    else:
        vec_out = [scalar_bounds(x[0], x[1]) for x in zip(vec, bounds)]
        vec_out = np.array(vec_out) if isinstance(vec, np.ndarray) else vec_out

    vec_out = np.reshape(vec_out, shape_reset) if paired_vector_check else vec_out

    return vec_out



def vector_limiter(
    vecs:list, 
    var_bounds: tuple
) -> list:
    """
    Bound a collection vectors by sum. Must specify at least a lower bound. 
        Renormalizes vector components that exceed a threshold. Reflects the
        concept of a limiter.

    Function Arguments
    ------------------
    - vecs: list of numpy arrays with the same shape
    - var_bounds: tuple of
    """

    types_valid = [tuple, list, np.ndarray]
    if not any([isinstance(var_bounds, x) for x in types_valid]):
        str_types_valid = format_print_list([str(x) for x in types_valid])
        raise ValueError(f"Invalid variable bounds type '{var_bounds}' in vector_limiter: valid types are {str_types_valid}")
    elif len(var_bounds) < 1:
        raise ValueError(f"Invalid bounds specification of length 0 found in vector_limiter. Enter at least a lower bound.")

    # get vector totals
    vec_total = 0
    for v in enumerate(vecs):
        i, v = v
        vecs[i] = np.array(v).astype(float)
        vec_total += vecs[i]

    # check for exceedance
    thresh_inf = var_bounds[0] if (var_bounds[0] is not None) else -np.inf
    thresh_sup = var_bounds[1] if (len(var_bounds) > 1) else np.inf
    thresh_sup = thresh_sup if (thresh_sup is not None) else np.inf

    # replace those beyond the infinum
    w_inf = np.where(vec_total < thresh_inf)[0]
    if len(w_inf) > 0:
        for v in vecs:
            elems_new = thresh_inf*v[w_inf]/vec_total[w_inf]
            np.put(v, w_inf, elems_new)

    # replace those beyond the supremum
    w_sup = np.where(vec_total > thresh_sup)[0]
    if len(w_sup) > 0:
        for v in vecs:
            elems_new = thresh_sup*v[w_sup]/vec_total[w_sup]
            np.put(v, w_sup, elems_new)

    return vecs



def zeros_to_small(
    vec_in: np.ndarray,
    axis: Union[int, None] = None,
    min_scale: float = 10**(-6),
    on_all_zeros_epsilon: Union[float, None] = None
) -> np.ndarray:
    """
    Replace zeros in `vec_in` with a very small value
    
    Keyword Arguments
    -----------------
    - axis: optional axis to use for determining minimum. If None, uses global
        minimum.
        * axis = 0 will replace with the minimum in the column
        * axis = 1 will replace with the minimum in the row
    - min_scale: scalar applied to minimum non-zero value to generate 
        replacements
    - on_all_zeros_epsilon: epsilon (very small float) to use in place of a 
        vector that is all zeros. If None, returns vec. 
    """
    
    vec = vec_in.copy().astype(float)
    vec = vec if (axis is None) else (
        vec.transpose() if (axis == 1) else vec
    )

    if (axis in [0, 1]) and (len(vec.shape) > 1):

        for i in range(vec.shape[1]):
            
            vec_new = zeros_to_small_vector(
                vec[:, i],
                min_scale = min_scale,
                on_all_zeros_epsilon = on_all_zeros_epsilon
            )

            vec[:, i] = vec_new

    else:

        vec = zeros_to_small_vector(
            vec,
            min_scale = min_scale,
            on_all_zeros_epsilon = on_all_zeros_epsilon
        )

    # re-transpose if necessary
    vec = vec if (axis is None) else (
        vec.transpose() if (axis == 1) else vec
    )
        
    return vec



def zeros_to_small_vector(
    vec_in: np.ndarray,
    min_scale: float = 10**(-6),
    on_all_zeros_epsilon: Union[float, None] = None
) -> np.ndarray:
    """
    Replace zeros in `vec_in` with a very small value
    
    Keyword Arguments
    -----------------
    - axis: optional axis to use for determining minimum. If None, uses global
        minimum.
        * axis = 0 will replace with the minimum in the column
        * axis = 1 will replace with the minimum in the row
    - min_scale: scalar applied to minimum non-zero value to generate 
        replacements
    - on_all_zeros_epsilon: epsilon (very small float) to use in place of a 
        vector that is all zeros. If None, returns vec. 
    """

    vec = vec_in.copy()
    w = np.where(vec > 0.0)

    m_val = (
        min(vec[w])*min_scale if (len(w[0]) > 0) else (
            on_all_zeros_epsilon
            if isinstance(on_all_zeros_epsilon, float) or isinstance(on_all_zeros_epsilon, int)
            else 0.0
        )
    )

    vec[vec == 0] = m_val

    return vec