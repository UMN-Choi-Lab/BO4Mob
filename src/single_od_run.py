# Standard library imports
import argparse
import os
import pprint
import subprocess
import sys
import warnings
from pathlib import Path

# Third-party imports
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from botorch.exceptions import BadInitialCandidatesWarning

# Local application imports
from simulation.data_loader import load_config_single_od_run, od_xml_to_df
from simulation.evaluation import run_single_od_evaluation
from utils.path_utils import prepare_run_paths
from utils.plot_utils import save_fit_to_gt_plots_single_run

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
    Run a single OD simulation using SUMO.

    This function handles:
    - Parsing command-line arguments including network, time, and OD input
    - Loading simulation configuration, OD matrices, route data, and sensor data
    - Running one simulation with the provided OD input (from --od_values or --od_csv)
    - Saving simulation results, including output flows and evaluation plots
    - (Optionally) launching SUMO-GUI to visualize the simulation using --launch_gui
    """
    # =====================
    # Parse command-line arguments
    # =====================
    parser = argparse.ArgumentParser(description="OD Calibration Single Run")
    parser.add_argument(
        "--network_name",
        type=str,
        default="1ramp",
        choices=["1ramp", "2corridor", "3junction", "4smallRegion", "5fullRegion"],
    )
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
        "--od_csv",
        type=str,
        required=False,
        help="Path to the OD CSV file. If not provided, the default path will be used.",
    )
    parser.add_argument(
        "--od_values",
        type=int,
        nargs=3,
        required=False,
        help="Three integer OD values for the 1ramp network (optional).",
    )
    parser.add_argument(
        "--launch_gui",
        action="store_true",
        help="If set, launches SUMO GUI after simulation using sumo_gui_runner.py",
    )
    args = parser.parse_args()
    print(args)

    # =====================
    # Set experiment settings
    # =====================
    date = args.date
    hour = args.hour
    network_name = args.network_name
    eval_measure = args.eval_measure
    routes_per_od = args.routes_per_od

    # =====================
    # Load configuration
    # =====================
    config = load_config_single_od_run(base_path, config_file_name=f"sim_setup_network_{args.network_name}.json")
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

    # Load ground-truth sensor flow data
    true_sensor_file_name = f"gt_link_data_{network_name}_{date}_{hour}.csv"
    sensor_measure_gt = pd.read_csv(base_path + f"/sensor_data/{date}/" + true_sensor_file_name)

    # Extract the list of links where sensors are located
    link_selection = sensor_measure_gt["link_id"].tolist()
    link_selection = list(map(str, link_selection))
    print(f"Number of sensors: {len(link_selection)}")

    # =====================
    # Set up paths for simulation run
    # =====================

    # Set up run paths
    if args.od_csv:
        od_file = args.od_csv
    elif args.network_name == "1ramp" and args.od_values:
        od_file = "od_" + "-".join(map(str, args.od_values))
    else:
        od_file = None

    path_run_detail, path_run_simul, path_run_result, path_existence = prepare_run_paths(
        config["path_run"], date, hour, eval_measure, routes_per_od, seed=None, od_file=od_file
    )

    if path_existence:
        print(f"Run already exists at {path_run_detail}. Exiting.")
    else:
        # =====================
        # Load target OD values
        # =====================
        if args.od_csv:
            od_file_path = os.path.join(base_path, f"od_for_single_run/{args.od_csv}")
            if os.path.exists(od_file_path):
                od_df_target = pd.read_csv(od_file_path)
                x = od_df_target["flow"].to_numpy()
                print(f"Loaded target OD values with {len(x)} flows.")
            else:
                raise FileNotFoundError(f"OD file not found: {od_file_path}")
        elif args.network_name == "1ramp" and args.od_values:
            if len(args.od_values) != 3:
                raise ValueError("Exactly three OD values must be provided for the 1ramp network.")
            x = args.od_values
            print(f"Using provided OD values for 1ramp: {x}")
        else:
            raise ValueError("Either a valid OD CSV file must be provided or OD values must be specified for 1ramp.")

        # =====================
        # Run simulation
        # =====================

        curr_link_stats = run_single_od_evaluation(
            x,
            od_df_base,
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
        )

        # =====================
        # Visualize results
        # =====================
        save_fit_to_gt_plots_single_run(eval_measure, x, sensor_measure_gt, curr_link_stats, path_run_detail, network_name)

    # =====================
    # Optionally launch SUMO GUI
    # =====================
    if args.launch_gui:
        print("[Info] Launching SUMO GUI...")

        # Determine `od_input` identifier used in the result folder name
        if args.od_csv:
            od_input = Path(args.od_csv).stem + "_csv"
        else:
            od_input = "od_" + "-".join(map(str, args.od_values)) + "_values"

        # Build command to launch SUMO GUI
        gui_cmd = [
            "python",
            "visualization/sumo_gui_runner.py",
            "--mode",
            "single_od_run",
            "--network_name",
            network_name,
            "--date",
            str(date),
            "--hour",
            hour,
            "--routes_per_od",
            routes_per_od,
            "--od_input",
            od_input,
        ]

        subprocess.run(gui_cmd)


if __name__ == "__main__":
    main()
