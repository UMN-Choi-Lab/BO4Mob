# Standard library imports
import math
from dataclasses import dataclass
from typing import Optional

# Third-party imports
import torch
from botorch.acquisition import qExpectedImprovement
from botorch.exceptions import ModelFittingError
from botorch.fit import fit_gpytorch_mll
from botorch.generation import MaxPosteriorSampling
from botorch.optim import optimize_acqf
from botorch.utils.transforms import unnormalize
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.settings import max_cholesky_size
from gpytorch.utils.errors import NotPSDError
from torch.quasirandom import SobolEngine

from models.gp_models import initialize_model

# Local application imports
from optimizers.base_strategy import BaseStrategy


@dataclass
class TurboState:
    """
    State object for TuRBO optimization.

    Manages trust region size, success/failure counters, and restart logic.
    """

    dim: int
    batch_size: int
    length: float = 0.8
    length_min: float = 0.5**7
    length_max: float = 1.6
    failure_counter: int = 0
    success_counter: int = 0
    success_tolerance: int = 3
    failure_tolerance: Optional[int] = None
    best_value: float = -float("inf")
    restart_triggered: bool = False

    def __post_init__(self):
        """Compute the initial failure tolerance based on dimensionality and batch size."""
        self.failure_tolerance = math.ceil(max(4.0 / self.batch_size, float(self.dim) / self.batch_size))


def update_state(state, Y_next):
    """Update the TuRBO state based on improvement in objective values."""
    improved = max(Y_next) > state.best_value + 1e-3 * abs(state.best_value)
    state.success_counter = state.success_counter + 1 if improved else 0
    state.failure_counter = 0 if improved else state.failure_counter + 1

    if state.success_counter == state.success_tolerance:
        state.length = min(2.0 * state.length, state.length_max)
        state.success_counter = 0
    elif state.failure_counter == state.failure_tolerance:
        state.length /= 2.0
        state.failure_counter = 0

    state.best_value = max(state.best_value, max(Y_next).item())
    state.restart_triggered = state.length < state.length_min
    return state


def optimize_acqf_and_create_candidate(
    state,
    model,
    X,
    Y,
    bounds,
    device,
    dtype,
    seed,
    batch_size,
    n_candidates=None,
    num_restarts=10,
    raw_samples=512,
    acqf="ts",
):
    """Optimize acquisition function within trust region and return new candidate points."""
    assert acqf in ("ts", "ei")
    assert X.min() >= 0.0 and X.max() <= 1.0 and torch.all(torch.isfinite(Y))

    x_center = X[Y.argmax(), :].clone()
    weights = model.covar_module.base_kernel.lengthscale.detach().view(-1)
    weights = weights / weights.mean()
    weights = weights / torch.prod(weights.pow(1.0 / len(weights)))

    tr_lb = torch.clamp(x_center - weights * state.length / 2.0, 0.0, 1.0)
    tr_ub = torch.clamp(x_center + weights * state.length / 2.0, 0.0, 1.0)

    if n_candidates is None:
        n_candidates = min(5000, max(2000, 200 * X.shape[-1]))

    if acqf == "ts":
        dim = X.shape[-1]
        sobol = SobolEngine(dim, scramble=True, seed=seed)
        pert = sobol.draw(n_candidates).to(dtype=dtype, device=device)
        pert = tr_lb + (tr_ub - tr_lb) * pert

        prob_perturb = min(20.0 / dim, 1.0)
        mask = torch.rand(n_candidates, dim, dtype=dtype, device=device) <= prob_perturb
        ind = torch.where(mask.sum(dim=1) == 0)[0]
        mask[ind, torch.randint(0, dim - 1, size=(len(ind),), device=device)] = 1

        X_cand = x_center.expand(n_candidates, dim).clone()
        X_cand[mask] = pert[mask]

        thompson_sampling = MaxPosteriorSampling(model=model, replacement=False)
        with torch.no_grad():
            X_new_fullD_norm = thompson_sampling(X_cand, num_samples=batch_size)

    elif acqf == "qei":
        qei = qExpectedImprovement(model, Y.max(), maximize=True)
        X_new_fullD_norm, _ = optimize_acqf(
            qei,
            bounds=torch.stack([tr_lb, tr_ub]),
            q=batch_size,
            num_restarts=num_restarts,
            raw_samples=raw_samples,
        )

    else:
        raise ValueError(f"Unknown acquisition function type: {acqf}")

    return unnormalize(X_new_fullD_norm, bounds)


def safe_fit_gp_model(mll, train_X, train_Y):
    """Fit the GP model safely, falling back to Adam optimizer if standard fitting fails."""
    try:
        fit_gpytorch_mll(mll)
    except (NotPSDError, RuntimeError, ModelFittingError):
        print("[Fallback] Using Adam optimizer due to GP fitting failure.")
        optimizer = torch.optim.Adam([{"params": mll.model.parameters()}], lr=0.1)
        for _ in range(100):
            optimizer.zero_grad()
            output = mll.model(train_X)
            loss = -mll(output, train_Y.flatten())
            loss.backward()
            optimizer.step()


class TurboStrategy(BaseStrategy):
    """
    TuRBO (Trust Region Bayesian Optimization) strategy.

    Uses local trust region-based candidate generation with Thompson sampling or qEI.
    """

    def initialize(self, X_init, Y_init, **kwargs):
        """Initialize TuRBO state based on input dimensionality and batch size."""
        self.state = TurboState(dim=X_init.shape[1], batch_size=self.params["bo_batch_size"])

    def suggest(self, X_all_fullD_norm, Y_all_real, kernel, epoch, seed):
        """
        Suggest new candidates using the current TuRBO state and GP surrogate model.

        Parameters
        ----------
        X_all_fullD_norm : torch.Tensor
            Normalized input history.
        Y_all_real : torch.Tensor
            Corresponding objective values.
        epoch : int
            Current optimization epoch.
        seed : int
            Random seed for reproducibility.

        Returns
        -------
        torch.Tensor
            New candidate points in original (unnormalized) input space.
        """
        print(f"X_all_fullD_norm: {X_all_fullD_norm}")

        gp_model = initialize_model("turbo", X_all_fullD_norm, Y_all_real, kernel=kernel)
        mll = ExactMarginalLogLikelihood(gp_model.likelihood, gp_model)

        with max_cholesky_size(self.params["cholesky_limit"]):
            safe_fit_gp_model(mll, X_all_fullD_norm, Y_all_real)

            X_new_fullD_real = optimize_acqf_and_create_candidate(
                state=self.state,
                model=gp_model,
                X=X_all_fullD_norm,
                Y=Y_all_real,
                bounds=self.bounds,
                device=self.device,
                dtype=self.dtype,
                seed=seed,
                batch_size=self.params["bo_batch_size"],
                n_candidates=self.params["bo_n_candidates"],
                num_restarts=self.params["bo_num_restarts"],
                raw_samples=self.params["bo_raw_samples"],
                acqf="ts",
            )

        return X_new_fullD_real

    def update(self, Y_new):
        """
        Update internal TuRBO state based on new objective values.

        Parameters
        ----------
        Y_new : torch.Tensor
            Newly observed objective values from last suggestion.
        """
        self.state = update_state(self.state, Y_next=Y_new)
