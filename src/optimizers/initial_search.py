# Standard library imports
import multiprocessing as mp
import os
import time

# Third-party imports
import pandas as pd
import torch
from botorch.utils.transforms import unnormalize

# Local application imports
from simulation.evaluation import run_initial_evaluation
from utils.misc import set_seed


def run_initial_search_procedure(
    config,
    model_name,
    dim_od,
    bounds,
    dtype,
    device,
    seed,
    n_init_search,
    cpu_max,
    od_df_base,
    base_path,
    routes_df,
    routes_per_od,
    eval_measure,
    sensor_measure_gt,
    link_selection,
    path_init_detail,
    path_init_simul,
    path_init_result,
    init_existence,
):
    """
    Run the initial search phase using Sobol sampling and parallel evaluation.

    This function generates Sobol samples, performs simulations in parallel,
    saves results to CSV, and returns the aggregated dataset. If the result already exists,
    it skips simulation and loads from disk.

    Parameters
    ----------
    config : dict
        Configuration dictionary for simulation and evaluation.
    model_name : str
        Name of the optimization strategy.
    dim_od : int
        Dimensionality of the OD vector.
    bounds : torch.Tensor
        Bounds for unnormalizing the input vectors.
    dtype : torch.dtype
        Torch data type for computation.
    device : torch.device
        Device to run computations on.
    seed : int
        Random seed for reproducibility.
    n_init_search : int
        Number of initial search samples.
    cpu_max : int
        Maximum number of CPU cores to use.
    od_df_base : pd.DataFrame
        Base OD matrix dataframe.
    base_path : Path
        Base experiment directory.
    routes_df : pd.DataFrame
        Route information dataframe.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    eval_measure : str
        Type of evaluation measurement (e.g., 'count', 'speed').
    sensor_measure_gt : pd.DataFrame
        Ground truth traffic measurement data.
    link_selection : list[str]
        List of sensor link IDs used in evaluation.
    path_init_detail : Path
        Directory to save metadata or runtime info.
    path_init_simul : Path
        Directory to store simulation outputs.
    path_init_result : Path
        Directory to store initial search results.
    init_existence : bool
        Flag indicating whether initial results already exist.

    Returns
    -------
    pd.DataFrame
        DataFrame containing the evaluated initial search dataset.
    """
    set_seed(seed)

    if (model_name == "initSearch") or (not init_existence):

        code_init_start_time = time.time()

        # Generate initial Sobol samples (normalized [0, 1])
        sobol = torch.quasirandom.SobolEngine(dimension=dim_od, scramble=True, seed=seed)
        X_init_fullD_norm = sobol.draw(n_init_search).to(dtype=dtype, device=device)

        # Unnormalize to real OD scale
        X_init_fullD_real = unnormalize(X_init_fullD_norm, bounds)

        # Prepare multiprocessing environment
        mp.freeze_support()
        with mp.Manager() as manager:
            lock = manager.Lock()
            ods_epsilon = manager.list()
            loss_all = manager.list()
            batch_data_i = manager.list()

            num_processes = min(mp.cpu_count() - 1, n_init_search + 1, cpu_max)
            base_od = od_df_base.copy()

            with mp.Pool(processes=num_processes) as pool:
                pool.starmap(
                    run_initial_evaluation,
                    [
                        (
                            i,
                            x,
                            base_od,
                            config,
                            base_path,
                            lock,
                            ods_epsilon,
                            loss_all,
                            batch_data_i,
                            str(path_init_simul),
                            routes_df,
                            routes_per_od,
                            link_selection,
                            eval_measure,
                            sensor_measure_gt,
                            dim_od,
                        )
                        for i, x in enumerate(X_init_fullD_real.cpu().tolist())
                    ],
                )

            # Save dataset
            data_set_init_search = pd.concat(batch_data_i)
            init_csv_file = path_init_result / "data_set.csv"
            data_set_init_search.to_csv(init_csv_file, index=False)
            print(f"[Saved] Initial search dataset: {init_csv_file}")

        # Save runtime
        code_init_duration = time.time() - code_init_start_time
        h, m = divmod(int(code_init_duration), 3600)
        m, s = divmod(m, 60)

        run_time_file_init = os.path.join(path_init_detail, f"code run time is {h}h {m}m {s}s.txt")
        with open(run_time_file_init, "w") as f:
            f.write(f"Total code run time: {h}h {m}m {s}s")

    else:
        print(f"[Skip] Initial search dataset already exists: {init_existence}")
        init_csv_file = path_init_result / "data_set.csv"
        data_set_init_search = pd.read_csv(init_csv_file)

    return data_set_init_search
