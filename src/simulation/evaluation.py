# Standard library imports
import os
import time
from pathlib import Path

# Third-party imports
import numpy as np
import pandas as pd

# Local application imports
from simulation.sumo_runner import create_od_tazrelation_xml, simulate_od
from utils.link_flow_analysis import compute_nrmse_all_links, parse_link_flow_xml_to_pandas


def run_initial_evaluation(
    i,
    x,
    base_od,
    config,
    base_path,
    lock,
    ods_epsilon,
    loss_all,
    batch_data_i,
    path_init_simul,
    routes_df,
    routes_per_od,
    link_selection,
    eval_measure,
    sensor_measure_gt,
    dim_od,
):
    """
    Run a simulation for an initial OD (Origin-Destination) sample and record the results.

    Parameters
    ----------
    i : int
        Index of the current initial sample.
    x : array-like
        OD demand values for the current sample.
    base_od : pd.DataFrame
        Base OD matrix DataFrame.
    config : dict
        Simulation and optimization configuration parameters.
    base_path : str
        Base directory for input/output files.
    lock : threading.Lock
        Lock object for multiprocessing (not used directly here).
    ods_epsilon : list
        List to collect all initial OD samples.
    loss_all : list
        List to collect all initial sample losses.
    batch_data_i : list
        List to collect DataFrames of sample metadata.
    path_init_simul : str
        Output path for initial search simulations.
    routes_df : pd.DataFrame
        Route information DataFrame.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    link_selection : list
        List of links selected for evaluation.
    eval_measure : str
        Type of evaluation measurement (e.g., 'count', 'speed').
    sensor_measure_gt : pd.DataFrame
        Ground truth sensor data for comparison.
    dim_od : int
        Dimension of OD matrix (number of OD pairs).

    Returns
    -------
    None
    """
    i += 1
    print(f"\n########### Initial OD Sample: {i} ###########")

    # Prepare file paths
    new_od_xml = f"{path_init_simul}/init_{i}_od.xml"
    prefix_output_simul = f"{path_init_simul}/init_{i}"

    # Prepare OD matrix
    curr_od = np.array(x)
    print(f"Total expected demand: {curr_od.sum():.1f}")

    base_od_copy = base_od.copy()
    base_od_copy["count"] = [round(elem, 1) for elem in curr_od]
    base_od_copy = base_od_copy.rename(columns={"fromTaz": "from", "toTaz": "to"})

    # Save OD as TAZ XML
    create_od_tazrelation_xml(
        od_df=base_od_copy,
        output_file=Path(new_od_xml),
        od_end_time_seconds=config["od_end_time"],
    )

    # Save current OD sample
    ods_epsilon.append(curr_od)

    # Run SUMO simulation
    start_time = time.time()
    simulate_od(
        new_od_xml,
        prefix_output_simul,
        base_path,
        config["net_xml"],
        config["taz_xml"],
        config["additional_xml"],
        routes_df,
        routes_per_od,
        config["sim_end_time"],
        config["trips_xml_out_str"],
    )
    run_time = time.time() - start_time

    # Load simulation output and compute loss
    sim_link_out = f"{base_path}/{prefix_output_simul}_{config['link_data_out_str']}"
    curr_link_stats, _, _ = parse_link_flow_xml_to_pandas(
        base_path,
        sim_link_out,
        prefix_output_simul,
        config["sensor_start_time"],
        config["sensor_end_time"],
        link_list=link_selection,
    )
    curr_loss = compute_nrmse_all_links(eval_measure, sensor_measure_gt, curr_link_stats)
    print(f"Loss: {curr_loss:.4f}")

    # Save loss
    loss_all.append(curr_loss)

    # Save sample metadata
    df_curr = pd.DataFrame(curr_od.reshape(1, -1), columns=[f"x_{j}" for j in range(1, dim_od + 1)])
    df_curr.insert(0, "init_search", i)
    df_curr.insert(1, "epoch", 0)
    df_curr.insert(2, "batch", 0)
    df_curr.insert(3, "loss", curr_loss)
    df_curr.insert(4, "run_time", run_time)
    df_curr.insert(5, "num_train_data", 0)
    batch_data_i.append(df_curr)

    # Clean up intermediate simulation files (optional)
    if config["eliminate_sumo_run_files"] == "True":
        trips_out = config["trips_xml_out_str"]
        try:
            os.remove(sim_link_out)
            os.remove(f"{base_path}/{prefix_output_simul}_{trips_out[:-4]}_beforeRteUpdates.xml")
            os.remove(f"{base_path}/{prefix_output_simul}_{trips_out}")
            # os.remove(f"{base_path}/{prefix_output_simul}_routes.vehroutes.xml")
        except FileNotFoundError:
            print("[Warning] Some intermediate files were not found during cleanup.")


def run_sample_evaluation(
    j,
    x_j,
    i,
    config,
    base_od,
    path_opt_simul,
    base_path,
    routes_df,
    routes_per_od,
    eval_measure,
    sensor_measure_gt,
    link_selection,
    num_train_data,
):
    """
    Run a simulation for a single sample and return loss and link statistics.

    Parameters
    ----------
    j : int
        Index of the current batch/sample.
    x_j : array-like
        OD demand values for the current BO sample.
    i : int
        Current epoch index.
    config : dict
        Simulation and optimization configuration parameters.
    base_od : pd.DataFrame
        Base OD matrix DataFrame.
    path_opt_simul : str
        Output path for simulations.
    base_path : str
        Base directory for input/output files.
    routes_df : pd.DataFrame
        Route information DataFrame.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    eval_measure : str
        Type of evaluation measurement (e.g., 'count', 'speed').
    sensor_measure_gt : pd.DataFrame
        Ground truth sensor measurement data for evaluation.
    link_selection : list
        List of links selected for evaluation.
    num_train_data : int
        Number of training data points collected so far.

    Returns
    -------
    tuple
        A tuple containing:

        - run_simul_info (list): Metadata about the simulation run
          (e.g., [strategy_id, epoch, batch, runtime, num_train_data]).
        - curr_loss (float): NRMSE loss between simulated and ground-truth link flows.
        - curr_link_stats (pd.DataFrame): DataFrame with detailed simulation results for each link.
    """
    print(f"\n##### Epoch {i} — Batch {j} #####")

    # Prepare file paths
    new_od_xml = f"{path_opt_simul}/opt_{i}_{j}_od.xml"
    prefix_output_simul = f"{path_opt_simul}/opt_{i}_{j}"

    # Prepare OD matrix
    curr_od = x_j
    base_od_copy = base_od.copy()
    base_od_copy["count"] = [round(elem, 1) for elem in curr_od]
    base_od_copy = base_od_copy.rename(columns={"fromTaz": "from", "toTaz": "to"})

    # Save OD as TAZ XML
    create_od_tazrelation_xml(
        od_df=base_od_copy,
        output_file=Path(new_od_xml),
        od_end_time_seconds=config["od_end_time"],
    )
    print(f"Total expected demand: {x_j.sum():.1f}")

    # Run SUMO simulation
    start_time = time.time()
    simulate_od(
        new_od_xml,
        prefix_output_simul,
        base_path,
        config["net_xml"],
        config["taz_xml"],
        config["additional_xml"],
        routes_df,
        routes_per_od,
        config["sim_end_time"],
        config["trips_xml_out_str"],
    )
    run_time = time.time() - start_time

    # Load simulation output and compute loss
    sim_link_out = f"{base_path}/{prefix_output_simul}_{config['link_data_out_str']}"
    curr_link_stats, _, _ = parse_link_flow_xml_to_pandas(
        base_path,
        sim_link_out,
        prefix_output_simul,
        config["sensor_start_time"],
        config["sensor_end_time"],
        link_list=link_selection,
    )
    curr_loss = compute_nrmse_all_links(eval_measure, sensor_measure_gt, curr_link_stats)
    print(f"Loss: {curr_loss:.4f} | Runtime: {run_time:.2f}s")

    # Annotate link stats
    run_simul_info = [0, i, j, run_time, num_train_data]
    curr_link_stats.insert(0, "epoch", i)
    curr_link_stats.insert(1, "batch", j)

    # Clean up intermediate simulation files (optional)
    if config["eliminate_sumo_run_files"] == "True":
        trips_out = config["trips_xml_out_str"]
        try:
            os.remove(sim_link_out)
            os.remove(f"{base_path}/{prefix_output_simul}_{trips_out[:-4]}_beforeRteUpdates.xml")
            os.remove(f"{base_path}/{prefix_output_simul}_{trips_out}")
            # os.remove(f"{base_path}/{prefix_output_simul}_routes.vehroutes.xml")  # for sumo gui visualization
        except FileNotFoundError:
            print("[Warning] Some intermediate files were not found during cleanup.")

    return run_simul_info, curr_loss, curr_link_stats


def run_single_od_evaluation(
    x,
    base_od,
    config,
    base_path,
    path_run_detail,
    path_run_simul,
    path_run_result,
    routes_df,
    routes_per_od,
    link_selection,
    eval_measure,
    sensor_measure_gt,
):
    """
    Run a simulation for a single OD (Origin-Destination) vector and record the results.

    Parameters
    ----------
    x : array-like
        OD demand values for the current sample.
    base_od : pd.DataFrame
        Base OD matrix DataFrame.
    config : dict
        Simulation and optimization configuration parameters.
    base_path : str
        Base directory for input/output files.
    path_run_detail : str
        Directory path to save runtime metadata.
    path_run_simul : str
        Directory path to save simulation outputs.
    path_run_result : str
        Directory path to save evaluation results.
    routes_df : pd.DataFrame
        Route information DataFrame.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    link_selection : list
        List of links selected for evaluation.
    sensor_flow_gt : pd.DataFrame
        Ground truth sensor data for comparison.

    Returns
    -------
    pd.DataFrame
        DataFrame containing simulated link flow statistics for the current OD sample.
    """
    print("\n########### Start simulation and evaluation ###########")

    # Prepare file paths
    new_od_xml = f"{path_run_simul}/od.xml"
    prefix_output_simul = f"{path_run_simul}/result"

    # Prepare OD matrix
    curr_od = np.array(x)
    print(f"Total expected demand: {curr_od.sum():.1f}")

    base_od_copy = base_od.copy()
    base_od_copy["count"] = [round(elem, 1) for elem in curr_od]
    base_od_copy = base_od_copy.rename(columns={"fromTaz": "from", "toTaz": "to"})

    # Save OD as TAZ XML
    create_od_tazrelation_xml(
        od_df=base_od_copy,
        output_file=Path(new_od_xml),
        od_end_time_seconds=config["od_end_time"],
    )

    # Run SUMO simulation
    start_time = time.time()
    simulate_od(
        new_od_xml,
        prefix_output_simul,
        base_path,
        config["net_xml"],
        config["taz_xml"],
        config["additional_xml"],
        routes_df,
        routes_per_od,
        config["sim_end_time"],
        config["trips_xml_out_str"],
    )
    run_time = time.time() - start_time

    # Save simulation run time to a file
    run_time_hours, rem = divmod(run_time, 3600)
    run_time_minutes, run_time_seconds = divmod(rem, 60)
    run_time_str = f"simulation run time {int(run_time_hours)}h {int(run_time_minutes)}m {int(run_time_seconds)}s"
    run_time_file = Path(path_run_detail) / f"{run_time_str}.txt"
    with open(run_time_file, "w") as f:
        f.write(run_time_str)

    # Load simulation output and compute loss
    sim_link_out = f"{base_path}/{prefix_output_simul}_{config['link_data_out_str']}"
    curr_link_stats, _, _ = parse_link_flow_xml_to_pandas(
        base_path,
        sim_link_out,
        prefix_output_simul,
        config["sensor_start_time"],
        config["sensor_end_time"],
        link_list=link_selection,
    )
    curr_loss = compute_nrmse_all_links(eval_measure, sensor_measure_gt, curr_link_stats)
    print(f"Loss: {curr_loss:.4f}")

    # Merge ground truth and simulated flow data
    if eval_measure == 'count':
        sensor_measure_gt_temp = sensor_measure_gt.rename(columns={"interval_nVehContrib": "flow_gt"})[["link_id", "flow_gt"]]
        curr_link_stats_temp = curr_link_stats.rename(columns={"interval_nVehContrib": "flow_simul"})[
            ["link_id", "flow_simul"]
        ]
    elif eval_measure == 'speed':
        sensor_measure_gt_temp = sensor_measure_gt.rename(columns={"interval_harmonicMeanSpeed": "speed_gt"})[["link_id", "speed_gt"]]
        curr_link_stats_temp = curr_link_stats.rename(columns={"interval_harmonicMeanSpeed": "speed_simul"})[
            ["link_id", "speed_simul"]
        ]
    merged_data = pd.merge(sensor_measure_gt_temp, curr_link_stats_temp, on="link_id", how="inner")

    # Save to CSV
    output_csv_path = Path(path_run_result) / "link_measure_compare.csv"
    merged_data.to_csv(output_csv_path, index=False)
    print(f"Link measure comparison saved to {output_csv_path}")

    # Save NRMSE loss to a file
    nrmse_file = Path(path_run_result) / f"NRMSE_{curr_loss:.4f}.txt"
    with open(nrmse_file, "w") as f:
        f.write(f"NRMSE: {curr_loss:.4f}")

    # Clean up intermediate simulation files (optional)
    if config["eliminate_sumo_run_files"] == "True":
        trips_out = config["trips_xml_out_str"]
        try:
            os.remove(sim_link_out)
            os.remove(f"{base_path}/{prefix_output_simul}_{trips_out[:-4]}_beforeRteUpdates.xml")
            os.remove(f"{base_path}/{prefix_output_simul}_{trips_out}")
            # os.remove(f"{base_path}/{prefix_output_simul}_routes.vehroutes.xml")
        except FileNotFoundError:
            print("[Warning] Some intermediate files were not found during cleanup.")

    return curr_link_stats
