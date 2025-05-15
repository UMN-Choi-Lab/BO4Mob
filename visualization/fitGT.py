import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os


def plot_fitGT(
    network_name,
    model_seed_dict,
    data_sets,
    sensor_flow_simul,
    gt_csv,
    fig_path
):
    
    data_sets_for_fitPlot = {
    key: df[df['epoch'] != 0]
    for key, df in data_sets.items()
}
    

    for model, seeds in model_seed_dict.items():
        plt.figure(figsize=(7, 5))
        combined_data = []

        for seed in seeds:
            min_loss_row = data_sets_for_fitPlot[(model, seed)].loc[data_sets_for_fitPlot[(model, seed)]['loss'].idxmin()]
            min_epoch = int(min_loss_row['epoch'])
            min_batch = int(min_loss_row['batch'])
            
            sensor_data = sensor_flow_simul[(model, seed)]
            filtered_data = sensor_data[
                (sensor_data['epoch'] == min_epoch) & (sensor_data['batch'] == min_batch)
            ]
            combined_data.append(filtered_data)

        combined_df = pd.concat(combined_data)
        
        mean_values = combined_df.groupby('link_id')['interval_nVehContrib'].mean().reset_index()
        std_values = combined_df.groupby('link_id')['interval_nVehContrib'].std().reset_index()

        merged_mean_df = gt_csv.merge(mean_values, on='link_id', suffixes=('_gt', '_simul'))
        merged_mean_df = merged_mean_df.merge(std_values.rename(columns={'interval_nVehContrib': 'std'}), on='link_id')

        max_gt_value = max(merged_mean_df['interval_nVehContrib_gt'].max(), merged_mean_df['interval_nVehContrib_simul'].max())
        min_gt_value = min(merged_mean_df['interval_nVehContrib_gt'].min(), merged_mean_df['interval_nVehContrib_simul'].min())
    
        plt.plot([min_gt_value, max_gt_value], [min_gt_value, max_gt_value], 'r-', label="45-degree line")
  
        plt.scatter(
            merged_mean_df['interval_nVehContrib_gt'],
            merged_mean_df['interval_nVehContrib_simul'],
            label=f"{model}",
            alpha=0.7
        )
        
        plt.errorbar(
            merged_mean_df['interval_nVehContrib_gt'],
            merged_mean_df['interval_nVehContrib_simul'],
            yerr=merged_mean_df['std'] / 2,
            fmt='o',
            alpha=1.0,
            label=f"{model} error",
            color='black'
        )

        if model == 'spsa':
            title_name = 'SPSA'
        elif model == 'vanillabo':
            title_name = 'Vanilla BO'
        elif model == 'turbo':
            title_name = 'TuRBO'
        elif model == 'saasbo':
            title_name = 'SAASBO'
        else:
            raise ValueError(f"Invalid model: {model}. Please provide one of ['spsa', 'vanillabo', 'turbo', 'saasbo'].")
  
        plt.xlabel("GT link flows", fontsize=20)
        plt.ylabel("Simulated link flows", fontsize=20)
        plt.title(f"Fit to GT | {title_name}", fontsize=16)
        plt.savefig(os.path.join(fig_path, f'FitGT_{network_name}_{model}.png'), dpi=300)
        plt.close()