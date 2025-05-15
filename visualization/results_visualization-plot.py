import argparse
import numpy as np
import pandas as pd
import os
from pathlib import Path
import matplotlib.pyplot as plt


# from matplotlib.ticker import ScalarFormatter

from convergence import plot_convergence
from fitGT import plot_fitGT

# =====================
# Path setup
# =====================

current_path = os.getcwd()
current_path = current_path.replace("\\visualization", "")
current_path = current_path.replace("\\", "/")

base_path = f"{current_path}/output/full_optimization"
fig_path = f"{current_path}/visualization/figures"
sensor_path = f"{current_path}/sensor_data"

if not os.path.exists(fig_path):
    os.makedirs(fig_path)

folders = [folder for folder in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, folder))]



def main():
    """
    This is a function that plots a picture of convergence and fit to ground truth for the result.
    
    """
    # =====================
    # Parse command-line arguments
    # =====================
    parser = argparse.ArgumentParser(description="Plot figures")
    parser.add_argument(
        "--network_name",
        type=str,
        default="2corridor",
        choices=["1ramp", "2corridor", "3junction", "4smallRegion", "5fullRegion"],
    )
    parser.add_argument(
        "--routes_per_od",
        type=str,
        default='single',
        choices=["single", "multiple"],
        help="Type of routes to use for the simulation",
    )
    parser.add_argument(
        "--hour",
        type=str,
        default="08-09",
        choices=["06-07", "08-09", "17-18"],
        help="Time for simulation",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="221014",
        help="Date for simulation",
    )  
    parser.add_argument(
        "--max_epoch",
        type=int,
        default=3,
        help="Maximum number of epochs for simulation",
    )  
    
    args = parser.parse_args()
    print(args)
    
    
    # =====================
    # Set experiment settings
    # =====================
    network_name = args.network_name
    routes_per_od = args.routes_per_od
    hour = args.hour
    date = args.date
    max_epoch = args.max_epoch
    
    
    # =====================
    # File and variables settings
    # =====================
    
    list_folder_name = [
        folder for folder in folders
        if network_name in folder and
        routes_per_od in folder and
        hour in folder and
        date in folder and
        'initSearch' not in folder
    ]
    
    net_name = f'{network_name}_'
    model_list = [folder.split(net_name)[1].split('_')[0] for folder in list_folder_name if net_name in folder]
    seeds_list = [folder.split('seed-')[1].split('_')[0] for folder in list_folder_name if 'seed-' in folder]
    
    all_data = pd.DataFrame({
        'Folder': list_folder_name,
        'Model': model_list,
        'Seed': seeds_list
    })
    
    model_seed_list = all_data[['Folder','Model', 'Seed']].values.tolist()
    
    
    data_sets = {
        (model, seed): pd.read_csv(
            f'{base_path}/{file_name}/result/data_set.csv'
        )[lambda df: df['epoch'] <= max_epoch]
        for file_name, model, seed in model_seed_list
    }
    
    model_seed_dict = all_data.groupby('Model')['Seed'].apply(list).to_dict()
    
    sensor_flow_simul = {
        (model, seed): pd.read_csv(
            f'{base_path}/{file_name}/result/sensor_flow_simul.csv'
        )[lambda df: df['epoch'] <= max_epoch]
        for file_name, model, seed in model_seed_list
    }

    gt_csv = pd.read_csv(f'{sensor_path}/{date}/gt_link_data_{network_name}_{date}_{hour}.csv')
    
    
    
    # =====================
    # (1) Convergence plot
    # =====================
    
    plot_convergence(
        network_name,
        model_seed_dict,
        data_sets,
        fig_path
    )
    
    # =====================
    # (2) Fit to GT plot
    # =====================
    
    plot_fitGT(
        network_name,
        model_seed_dict,
        data_sets,
        sensor_flow_simul,
        gt_csv,
        fig_path
    )

    print("All plots have been generated successfully.")
    
if __name__ == "__main__":
    main()