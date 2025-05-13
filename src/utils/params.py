# Third-party imports
import torch

# Local application imports
from optimizers.turbo import TurboState  # If Turbo is used


def get_params(model_name, config, dim_od, device, dtype):
    """
    Return common and model-specific parameters for a given optimization strategy.

    Parameters
    ----------
    model_name : str
        Name of the model or optimization strategy (e.g., 'spsa', 'vanillabo', 'saasbo', 'turbo').
    config : dict
        Configuration dictionary including optimization settings and bounds.
    dim_od : int
        Dimensionality of the OD (origin-destination) vector.
    device : torch.device
        Device to place the parameter tensors on.
    dtype : torch.dtype
        Data type for tensors.

    Returns
    -------
    dict
        Dictionary containing strategy-specific parameters and common bounds.
    """
    common_params = {
        "bounds": torch.tensor(
            [[config["od_bound_start"]] * dim_od, [config["od_bound_end"]] * dim_od],
            device=device,
            dtype=dtype,
        ),
        "n_epoch": config["n_epoch"],
        "n_init_search": config["n_init_search"],
    }

    model_specific = {
        "spsa": lambda: {
            "spsa_params": {
                "A": int(common_params["n_epoch"] / 10),
                "alpha": 0.602,
                "a": round(0.05 * ((1 + int(common_params["n_epoch"] / 10)) ** 0.602), 2),
                "c": 0.1,
                "gamma": 0.101,
            }
        },
        "vanillabo": lambda: {
            "bo_batch_size": config["bo_batch_size"],
            "bo_num_restarts": config["bo_num_restarts"],
            "bo_raw_samples": config["bo_raw_samples"],
            "bo_sample_shape": config["bo_sample_shape"],
            "cholesky_limit": float("inf"),
        },
        "saasbo": lambda: {
            "bo_batch_size": config["bo_batch_size"],
            "bo_num_restarts": config["bo_num_restarts"],
            "bo_raw_samples": config["bo_raw_samples"],
            "bo_warmup_steps": 32,
            "bo_num_samples": 16,
            "bo_thinning": 16,
        },
        "turbo": lambda: {
            "bo_batch_size": config["bo_batch_size"],
            "bo_num_restarts": config["bo_num_restarts"],
            "bo_raw_samples": config["bo_raw_samples"],
            "bo_n_candidates": min(5000, max(2000, 200 * dim_od)),
            "cholesky_limit": float("inf"),
            "state": TurboState(dim_od, config["bo_batch_size"]),
        },
    }

    params = common_params.copy()
    if model_name in model_specific:
        params.update(model_specific[model_name]())

    return params
