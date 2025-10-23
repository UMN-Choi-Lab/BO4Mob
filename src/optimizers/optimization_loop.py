# Standard library imports
import multiprocessing as mp
import os
import time

# Third-party imports
import numpy as np
import pandas as pd
import torch
from botorch.utils.transforms import normalize
from tqdm import trange

# Local application imports
from optimizers.strategy_registry import strategy_registery
from simulation.evaluation import run_sample_evaluation
from utils.misc import set_seed


def run_optimization_loop(
    config,
    model_name,
    kernel,
    dim_od,
    params,
    bounds,
    dtype,
    device,
    seed,
    cpu_max,
    data_set_init_search,
    od_df_base,
    base_path,
    routes_df,
    routes_per_od,
    eval_measure,
    sensor_measure_gt,
    link_selection,
    path_opt_simul,
    path_opt_result,
    path_opt_detail,
):
    """
    Run a full optimization loop over multiple epochs using the specified optimization strategy.

    Parameters
    ----------
    config : dict
        Configuration dictionary for simulation and optimization.
    model_name : str
        Key for selecting the optimization strategy from the registry.
    kernel : str
        Kernel type for the GP model (e.g., 'matern-1.5', 'matern-2.5', 'rbf', 'None').
    dim_od : int
        Dimension of the OD (origin-destination) variables.
    params : dict
        Parameter dictionary including number of epochs and batch size.
    bounds : Tensor
        Bounds for normalization of input variables.
    dtype : torch.dtype
        Torch data type for tensors.
    device : torch.device
        Torch device ('cpu' or 'cuda').
    seed : int
        Random seed for reproducibility.
    cpu_max : int
        Maximum number of CPU processes to use.
    data_set_init_search : pd.DataFrame
        Initial dataset used to start the optimization loop.
    od_df_base : pd.DataFrame
        Base OD DataFrame used as input for simulations.
    base_path : Path
        Root directory of the experiment.
    routes_df : pd.DataFrame
        Route definitions used in the simulation.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    eval_measure : str
        Evaluation measure used for optimization (e.g., 'sensor', 'link').
    sensor_measure_gt : pd.DataFrame
        Ground truth sensor measurement data.
    link_selection : list[str]
        List of links used for evaluation.
    path_opt_simul : Path
        Path to the simulation output directory.
    path_opt_result : Path
        Path to save optimization results (e.g., CSV files).
    path_opt_detail : Path
        Path to save runtime statistics and logs.

    Returns
    -------
    pd.DataFrame
        Final optimization dataset containing simulation and optimization results.
    pd.DataFrame
        Aggregated sensor flow statistics from all epochs.
    """
    code_opt_start_time = time.time()
    n_epoch = params["n_epoch"]

    # Prepare training data
    X_all_fullD_real = torch.tensor(data_set_init_search.filter(like="x_").values, dtype=dtype, device=device)
    Y_all_real = -torch.tensor(data_set_init_search[["loss"]].values, dtype=dtype, device=device)

    run_simul_info_total = data_set_init_search[
        ["init_search", "epoch", "batch", "run_time", "num_train_data"]
    ].to_numpy()
    sensor_measure_simul = pd.DataFrame(
        columns=[
            "epoch",
            "batch",
            "link_id",
            "interval_nVehContrib",
            "interval_harmonicMeanSpeed",
        ]
    )
    model_run_time_df = pd.DataFrame(columns=["epoch", "num_train_data", "run_time"])

    # Instantiate strategy
    strategy_class = strategy_registery[model_name]
    strategy = strategy_class(params, config, bounds, device, dtype)
    strategy.initialize(
        X_all_fullD_real,
        Y_all_real,
        base_od=od_df_base.copy(),
        path_opt_simul=path_opt_simul,
        path_opt_result=path_opt_result,
        base_path=base_path,
        routes_df=routes_df,
        routes_per_od=routes_per_od,
        eval_measure=eval_measure,
        sensor_measure_gt=sensor_measure_gt,
        link_selection=link_selection,
    )

    for i in trange(1, n_epoch + 1, desc="Optimization Loop"):
        seed_i = seed + i
        set_seed(seed_i)
        print(f"\n>>> Optimization epoch {i}")
        num_train_data = len(Y_all_real)

        model_run_time_start = time.time()
        X_all_fullD_norm = normalize(X_all_fullD_real, bounds)
        X_new_fullD_real = strategy.suggest(X_all_fullD_norm, Y_all_real, kernel=kernel, epoch=i, seed=seed_i)
        model_run_time = time.time() - model_run_time_start

        model_run_time_new_row = pd.DataFrame(
            [{"epoch": i, "num_train_data": num_train_data, "run_time": model_run_time}]
        )
        if model_run_time_df.empty:
            model_run_time_df = model_run_time_new_row.copy()
        else:
            model_run_time_df = pd.concat([model_run_time_df, model_run_time_new_row], ignore_index=True)

        # Run simulations
        base_od = od_df_base.copy()

        if model_name == "spsa":
            with mp.Pool(processes=1) as pool:
                results = pool.starmap(
                    run_sample_evaluation,
                    [
                        (
                            3,
                            X_new_fullD_real[0],
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
                        )
                    ],
                )
            X_new_fullD_real = X_new_fullD_real.reshape(1, -1)

        else:
            if X_new_fullD_real.sum() == 0:
                print("All-zero sample, skipping.")
                continue

            X_new_fullD_real = X_new_fullD_real.cpu().numpy()
            num_processes = min(mp.cpu_count() - 1, params["bo_batch_size"] + 1, cpu_max)
            with mp.Pool(processes=num_processes) as pool:
                results = pool.starmap(
                    run_sample_evaluation,
                    [
                        (
                            j,
                            X_new_fullD_real[j - 1],
                            i,
                            config,
                            base_od,
                            str(path_opt_simul),
                            base_path,
                            routes_df,
                            routes_per_od,
                            eval_measure,
                            sensor_measure_gt,
                            link_selection,
                            num_train_data,
                        )
                        for j in range(1, params["bo_batch_size"] + 1)
                    ],
                )

        # Update datasets
        run_simul_info_batch = [res[0] for res in results if res]
        curr_loss_batch = [res[1] for res in results if res]
        curr_loop_stats_batch_df = pd.concat([res[2] for res in results if res], ignore_index=True)

        X_all_fullD_real = torch.cat([X_all_fullD_real, torch.tensor(X_new_fullD_real, dtype=dtype)], dim=0)
        Y_new_real = -torch.tensor(curr_loss_batch, dtype=dtype).unsqueeze(-1)
        Y_all_real = torch.cat([Y_all_real, Y_new_real], dim=0)

        run_simul_info_total = np.vstack([run_simul_info_total, np.array(run_simul_info_batch)])
        if sensor_measure_simul.empty:
            sensor_measure_simul = curr_loop_stats_batch_df.copy()
        else:
            sensor_measure_simul = pd.concat([sensor_measure_simul, curr_loop_stats_batch_df], ignore_index=True)

        if hasattr(strategy, "update"):
            strategy.update(Y_new_real)

        # Save results
        data_np = np.concatenate([run_simul_info_total, Y_all_real.numpy(), X_all_fullD_real.numpy()], axis=1)
        columns = [
            "init_search",
            "epoch",
            "batch",
            "run_time",
            "num_train_data",
            "loss",
        ] + [f"x_{j}" for j in range(1, dim_od + 1)]
        data_set_total = pd.DataFrame(data_np, columns=columns)
        data_set_total["loss"] = data_set_total["loss"] * (-1)

        data_set_total.to_csv(path_opt_result / "data_set.csv", index=False)
        sensor_measure_simul.to_csv(path_opt_result / "sensor_measure_simul.csv", index=False)
        model_run_time_df.to_csv(path_opt_result / "model_run_time.csv", index=False)

        print(f"[Saved] Epoch {i} results")

    # Save runtime
    code_opt_duration = time.time() - code_opt_start_time
    h, m = divmod(int(code_opt_duration), 3600)
    m, s = divmod(m, 60)
    run_time_file = os.path.join(path_opt_detail, f"code run time is {h}h {m}m {s}s.txt")
    with open(run_time_file, "w") as f:
        f.write(f"Total code run time: {h}h {m}m {s}s")

    return data_set_total, sensor_measure_simul
