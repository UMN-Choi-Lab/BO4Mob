# Standard library imports
import argparse
import os
import pprint
import sys
import warnings
from pathlib import Path

# Third-party imports
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import torch
from botorch.exceptions import BadInitialCandidatesWarning

# Local application imports
from optimizers.initial_search import run_initial_search_procedure
from optimizers.optimization_loop import run_optimization_loop
from simulation.data_loader import load_config_full_opt, od_xml_to_df
from utils.params import get_params
from utils.path_utils import prepare_run_paths
from utils.plot_utils import save_convergence_plot, save_fit_to_gt_plots

matplotlib.use("Agg")
plt.ioff()
warnings.filterwarnings("ignore", category=BadInitialCandidatesWarning)


# =====================
# SUMO Environment Setup
# =====================

# Set SUMO installation path (edit this according to your OS/environment)
default_sumo_paths = [
    "/opt/sumo-1.12/share/sumo",  # Linux
    "C:/Program Files (x86)/Eclipse/Sumo",  # Windows
]

sumo_home = os.environ.get("SUMO_HOME")
if not sumo_home:
    sumo_home = next((p for p in default_sumo_paths if os.path.exists(p)), None)
    if not sumo_home:
        sys.exit("SUMO_HOME is not set and no default path exists.")
    os.environ["SUMO_HOME"] = sumo_home

os.environ["LIBSUMO_AS_TRACI"] = "1"  # Optional: faster simulation

# Add SUMO tools to Python path
tools_path = os.path.join(os.environ["SUMO_HOME"], "tools")
if os.path.exists(tools_path):
    sys.path.append(tools_path)
else:
    sys.exit(f"Cannot find SUMO tools at {tools_path}")


# =====================
# Set Project Base Path
# =====================

project_root = Path(__file__).resolve().parent.parent
base_path = str(project_root)

# Check for whitespace in path (SUMO limitation)
if " " in base_path:
    raise ValueError("base_path should not contain spaces. SUMO does not support whitespace in paths.")

# Set working directory
os.chdir(project_root)


# =====================
# Main Function
# =====================


def main():
    """
    Run the full optimization pipeline for OD estimation using SUMO.

    This includes parsing arguments, loading configuration and data,
    performing initial search, running the chosen optimizer (e.g., SPSA, SAASBO, etc.),
    and visualizing results such as convergence plots and flow fit plots.
    """
    # =====================
    # Parse command-line arguments
    # =====================
    parser = argparse.ArgumentParser(description="OD Calibration Optimization")
    parser.add_argument(
        "--network_name",
        type=str,
        default="1ramp",
        choices=["1ramp", "2corridor", "3junction", "4smallRegion", "5fullRegion"],
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="spsa",
        choices=["initSearch", "spsa", "vanillabo", "saasbo", "turbo"],
    )
    parser.add_argument("--kernel", type=str, default="matern-2p5", choices=["matern-1p5", "matern-2p5", "rbf", "none"])
    parser.add_argument("--seed", type=int, default=33, help="Random seed for reproducibility")
    parser.add_argument("--date", type=int, default=221014, help="Date for simulation")
    parser.add_argument(
        "--hour",
        type=str,
        default="08-09",
        choices=["06-07", "08-09", "17-18"],
        help="Time for simulation",
    )
    parser.add_argument(
        "--eval_measure",
        type=str,
        default="count",
        choices=["count", "speed"],
        help="Evaluation measurements"
    )
    parser.add_argument(
        "--routes_per_od",
        type=str,
        default='single',
        choices=["single", "multiple"],
        help="Type of routes to use for the simulation",
    )
    parser.add_argument(
        "--cpu_max",
        type=int,
        default=6,
        help="Maximum number of CPU cores for parallel processing",
    )
    args = parser.parse_args()
    print(args)

    # =====================
    # Set experiment settings
    # =====================
    seed = args.seed
    date = args.date
    hour = args.hour
    model_name = args.model_name
    kernel = args.kernel
    network_name = args.network_name
    eval_measure = args.eval_measure
    routes_per_od = args.routes_per_od
    cpu_max = args.cpu_max

    # =====================
    # Load configuration
    # =====================
    config = load_config_full_opt(
        base_path,
        model_name=model_name,
        kernel=kernel,
        config_file_name=f"sim_setup_network_{args.network_name}.json",
    )
    pprint.pprint(dict(config))

    # =====================
    # Load input data
    # =====================

    # Load base OD matrix from XML
    od_df_base = od_xml_to_df(config["od_xml"])

    # Number of OD pairs (rows in the OD matrix)
    dim_od = od_df_base.shape[0]
    print(f"Number of OD pairs: {dim_od}")

    # Load precomputed route data from CSV
    routes_csv = config["routes_csv"]
    if routes_per_od == 'single':
        routes_csv = routes_csv.with_name("routes_single.csv")
    elif routes_per_od == 'multiple':
        routes_csv = routes_csv.with_name("routes_multiple.csv")
    routes_df = pd.read_csv(routes_csv, index_col=0)

    # Load ground-truth sensor measurements
    true_sensor_file_name = f"gt_link_data_{network_name}_{date}_{hour}.csv"
    sensor_measure_gt = pd.read_csv(base_path + f"/sensor_data/{date}/" + true_sensor_file_name)

    # Extract the list of links where sensors are located
    link_selection = sensor_measure_gt["link_id"].tolist()
    print(f"Number of sensors: {len(link_selection)}")

    # =====================
    # Set device, dtype, and load model-specific parameters
    # =====================
    device = torch.device("cpu")
    dtype = torch.double
    print(f"Using device: {device}")

    params = get_params(model_name, config, dim_od, device, dtype)

    bounds = params["bounds"]
    n_init_search = params["n_init_search"]

    # =====================
    # Set up paths for simulation run
    # =====================

    # Set up initial search paths
    path_init_detail, path_init_simul, path_init_result, init_existence = prepare_run_paths(
        config["path_init"], date, hour, eval_measure, routes_per_od, seed
    )

    # Set up optimization paths
    path_opt_detail, path_opt_simul, path_opt_result, _ = prepare_run_paths(
        config["path_opt"], date, hour, eval_measure, routes_per_od, seed
    )

    # =====================
    # Run initial search and optimization model
    # =====================

    # Run initial search procedure
    data_set_init_search = run_initial_search_procedure(
        config=config,
        model_name=model_name,
        dim_od=dim_od,
        bounds=bounds,
        dtype=dtype,
        device=device,
        seed=seed,
        n_init_search=n_init_search,
        cpu_max=cpu_max,
        od_df_base=od_df_base,
        base_path=base_path,
        routes_df=routes_df,
        routes_per_od=routes_per_od,
        eval_measure=eval_measure,
        sensor_measure_gt=sensor_measure_gt,
        link_selection=link_selection,
        path_init_detail=path_init_detail,
        path_init_simul=path_init_simul,
        path_init_result=path_init_result,
        init_existence=init_existence,
    )

    # Run optimization loop
    if model_name != "initSearch":
        data_set_total, sensor_measure_simul = run_optimization_loop(
            config=config,
            model_name=model_name,
            kernel=kernel,
            dim_od=dim_od,
            params=params,
            bounds=bounds,
            dtype=dtype,
            device=device,
            seed=seed,
            cpu_max=cpu_max,
            data_set_init_search=data_set_init_search,
            od_df_base=od_df_base,
            base_path=base_path,
            routes_df=routes_df,
            routes_per_od=routes_per_od,
            eval_measure=eval_measure,
            sensor_measure_gt=sensor_measure_gt,
            link_selection=link_selection,
            path_opt_simul=path_opt_simul,
            path_opt_result=path_opt_result,
            path_opt_detail=path_opt_detail,
        )

        # Result visualization
        save_convergence_plot(data_set_total, path_opt_detail)
        save_fit_to_gt_plots(
            eval_measure,
            data_set_total,
            sensor_measure_simul,
            sensor_measure_gt,
            path_opt_detail,
            network_name,
        )


if __name__ == "__main__":
    main()
