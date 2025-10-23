# Standard library imports
import multiprocessing as mp

# Third-party imports
import numpy as np
import torch
from botorch.utils.transforms import normalize, unnormalize

# Local application imports
from optimizers.base_strategy import BaseStrategy
from simulation.evaluation import run_sample_evaluation


def spsa_update(d, a=0.2, c=0.1, A=10, alpha=0.602, gamma=0.101, k=0):
    """
    Single SPSA update step (returns perturbed OD vectors and internal params).

    Parameters
    ----------
    f : Callable
        Objective function to optimize.
    d : np.ndarray
        Current OD vector (normalized between 0 and 1).
    a : float
        Learning rate scaling factor.
    c : float
        Perturbation scaling factor.
    A : float
        Stability constant.
    alpha : float
        Learning rate decay exponent.
    gamma : float
        Perturbation decay exponent.
    k : int
        Current iteration number.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, float, float, np.ndarray]
        Tuple containing (d_plus, d_minus, ak, ck, delta).
    """
    n = len(d)
    ak = a / ((k + 1 + A) ** alpha)
    ck = c / ((k + 1) ** gamma)

    delta = 2 * np.random.randint(0, 2, size=n) - 1
    d_plus = np.clip(d + ck * delta, 0, 1)
    d_minus = np.clip(d - ck * delta, 0, 1)

    print(f"[SPSA Iter {k}] ak={ak:.4f}, ck={ck:.4f}, Δ=±1, OD min={d.min():.2f}, max={d.max():.2f}")

    return d_plus, d_minus, ak, ck, delta


class SPSAStrategy(BaseStrategy):
    """
    SPSA-based Optimization strategy.

    This strategy uses Simultaneous Perturbation Stochastic Approximation to suggest
    new candidate solutions by estimating gradients using two-point perturbations.
    """

    def initialize(
        self,
        X_init,
        Y_init,
        base_od,
        path_opt_simul,
        path_opt_result,
        base_path,
        routes_df,
        routes_per_od,
        eval_measure,
        sensor_measure_gt,
        link_selection,
    ):
        """
        Initialize the SPSA strategy using the best initial solution and experiment context.

        Parameters
        ----------
        X_init : torch.Tensor
            Initial set of input vectors.
        Y_init : torch.Tensor
            Corresponding objective values.
        base_od : pd.DataFrame
            Base OD dataframe for simulation.
        path_opt_simul : Path
            Path for simulation outputs.
        path_opt_result : Path
            Path to store optimization results.
        base_path : Path
            Base experiment path.
        routes_df : pd.DataFrame
            Route data.
        routes_per_od : str
            Type of routes to use for the simulation (single or multiple).
        eval_measure : str
            Evaluation measure used for optimization (e.g., 'count', 'speed').
        sensor_measure_gt : pd.DataFrame
            Ground truth traffic measurement data.
        link_selection : list[str]
            List of link IDs used in evaluation.
        """
        best_idx = Y_init.argmax().item()
        initial_solution = X_init[best_idx].cpu().numpy()
        self.d_k = normalize(torch.tensor(initial_solution, dtype=self.dtype), self.bounds).numpy()

        # Store externally provided variables as attributes
        self.base_od = base_od
        self.path_opt_simul = path_opt_simul
        self.path_opt_result = path_opt_result
        self.base_path = base_path
        self.routes_df = routes_df
        self.routes_per_od = routes_per_od
        self.eval_measure = eval_measure
        self.sensor_measure_gt = sensor_measure_gt
        self.link_selection = link_selection

    def suggest(self, X_all_fullD_norm, Y_all_real, kernel, epoch, seed):
        """
        Suggest new candidate point using SPSA gradient approximation.

        Parameters
        ----------
        X_all_fullD_norm : torch.Tensor
            Normalized history of all X values.
        Y_all_real : torch.Tensor
            Observed objective values.
        epoch : int
            Current epoch index.
        seed : int
            Random seed for reproducibility.

        Returns
        -------
        np.ndarray
            A single suggested candidate OD vector (unnormalized).
        """
        k = epoch - 1
        d_plus, d_minus, ak, ck, delta = spsa_update(self.d_k, k=k, **self.params["spsa_params"])

        x_plus = unnormalize(torch.tensor(d_plus), self.bounds).numpy()
        x_minus = unnormalize(torch.tensor(d_minus), self.bounds).numpy()

        # Run two evaluations in parallel
        with mp.Pool(processes=2) as pool:
            results_temp = pool.starmap(
                run_sample_evaluation,
                [
                    (
                        1,
                        x_plus,
                        epoch,
                        self.config,
                        self.base_od,
                        self.path_opt_simul,
                        self.base_path,
                        self.routes_df,
                        self.routes_per_od,
                        self.eval_measure,
                        self.sensor_measure_gt,
                        self.link_selection,
                        len(Y_all_real),
                    ),
                    (
                        2,
                        x_minus,
                        epoch,
                        self.config,
                        self.base_od,
                        self.path_opt_simul,
                        self.base_path,
                        self.routes_df,
                        self.routes_per_od,
                        self.eval_measure,
                        self.sensor_measure_gt,
                        self.link_selection,
                        len(Y_all_real),
                    ),
                ],
            )

        # Compute gradient estimate from finite differences
        f_plus, f_minus = results_temp[0][1], results_temp[1][1]
        g_k = (f_plus - f_minus) / (2 * ck * delta)

        # Update normalized solution and convert back to real scale
        self.d_k = np.clip(self.d_k - ak * g_k, 0, 1)
        X_new_fullD_real = unnormalize(torch.tensor(self.d_k), self.bounds).numpy().reshape(1, -1)

        return X_new_fullD_real
