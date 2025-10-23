# Standard library imports
from pathlib import Path


def prepare_run_paths(base_path, date, hour, eval_measure, routes_per_od, seed=None, od_file=None):
    """
    Prepare output directory structure for a simulation run.

    The directory name is constructed from date, hour, and optionally a seed or OD file name.
    If `od_file` is provided and `seed` is None, the directory name reflects the OD file instead of a seed.

    Parameters
    ----------
    base_path : str or Path
        Base directory to contain simulation and result outputs.
    date : int
        Date for simulation, e.g., 221014 (YYMMDD).
    hour : str
        Time range for simulation, e.g., "08-09", "17-18".
    routes_per_od : str
        Type of routes per OD, e.g., "single" or "multiple".
    seed : Optional[int], default=None
        Random seed for reproducibility. If provided, used in the directory name.
    od_file : Optional[str], default=None
        File name or identifier for OD input. Used in directory naming when seed is None.

    Returns
    -------
    Tuple[Path, Path, Path, bool]
        A tuple containing:
        - Path to the detail directory
        - Path to the simulation subdirectory
        - Path to the result subdirectory
        - Boolean flag indicating whether the directory already existed
    """
    if seed is None and od_file is not None:
        if od_file.endswith(".csv"):
            detail_path = Path(f"{base_path}{date}_{hour}_{eval_measure}_{routes_per_od}_{od_file[:-4]}_csv")
        else:
            detail_path = Path(f"{base_path}{date}_{hour}_{eval_measure}_{routes_per_od}_{od_file}_values")
    else:
        detail_path = Path(
            f"{base_path}{date}_{hour}_{eval_measure}_{routes_per_od}" + (f"_seed-{seed:02d}" if seed is not None else "")
        )
    simul_path = detail_path / "simulation"
    result_path = detail_path / "result"
    existence = detail_path.exists()

    simul_path.mkdir(parents=True, exist_ok=True)
    result_path.mkdir(parents=True, exist_ok=True)

    return detail_path, simul_path, result_path, existence
