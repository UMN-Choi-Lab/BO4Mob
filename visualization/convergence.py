import numpy as np
import matplotlib.pyplot as plt
import os

def plot_convergence(
    network_name,
    model_seed_dict,
    data_sets,
    fig_path
):

    plt.figure(figsize=(5.5,5))

    y_max = float('-inf')

    for model in model_seed_dict.keys():
        model_data = [data_sets[(model, seed)] for seed in  model_seed_dict.get(model, [])]
        iterations = model_data[0]['epoch']
        
        try:
            losses = np.array([data['loss'].cummin() for data in model_data])
        except Exception as e:
            print(f"An error occurred while processing losses for model '{model}'\n Please check the minimum epoch value.")
            losses = np.array([])
            
        mean_loss = losses.mean(axis=0)
        std_loss = losses.std(axis=0)
        
                
        #> plt
        plt.plot(iterations, mean_loss, label=f"{model}", linewidth=1)
        
        plt.fill_between(iterations, mean_loss - 0.5 * std_loss, mean_loss + 0.5 * std_loss, alpha=0.3)
        
        y_max = max(y_max, mean_loss.max())

    plt.yscale('log')
    plt.title(f'Convergence Plot | {network_name}', fontsize=15)
    
    handles, labels = plt.gca().get_legend_handles_labels()
    labels = [
        "SPSA" if label.lower() == "spsa" else
        "Vanilla BO" if label.lower() == "vanillabo" else
        "TuRBO" if label.lower() == "turbo" else
        "SAASBO" if label.lower() == "saasbo" else label
        for label in labels
    ]
    plt.legend(handles, labels, fontsize=12)
    
    plt.xlabel('Epoch', fontsize=20)
    plt.ylabel('NRMSE', fontsize=20)
    
    plt.savefig(os.path.join(fig_path, f'convergence_plot_{network_name}.png'), dpi=300)
    plt.close()
