# Third-party imports
import torch
from botorch.acquisition.logei import qLogExpectedImprovement
from botorch.exceptions import ModelFittingError
from botorch.fit import fit_gpytorch_mll
from botorch.optim import optimize_acqf
from botorch.sampling.stochastic_samplers import StochasticSampler
from botorch.utils.transforms import unnormalize
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.settings import max_cholesky_size
from gpytorch.utils.errors import NotPSDError

from models.gp_models import initialize_model

# Local application imports
from optimizers.base_strategy import BaseStrategy


def optimize_acqf_and_create_candidate(acq_func, bounds, device, dtype, batch_size, num_restarts, raw_samples):
    """
    Optimize the acquisition function and return new candidate points (vanillabo version).

    Parameters
    ----------
    acq_func : AcquisitionFunction
        Acquisition function to optimize.
    bounds : torch.Tensor
        Tensor defining the bounds.
    device : torch.device
        Device to use.
    dtype : torch.dtype
        Data type to use.
    batch_size : int
        Batch size.
    num_restarts : int
        Number of restarts for optimization.
    raw_samples : int
        Number of raw samples.

    Returns
    -------
    torch.Tensor
        New candidate points (unnormalized).
    """
    dim = acq_func.model.train_inputs[0].size(dim=1)
    X_new_fullD_norm, _ = optimize_acqf(
        acq_func,
        bounds=torch.tensor([[0.0] * dim, [1.0] * dim], device=device, dtype=dtype),
        q=batch_size,
        num_restarts=num_restarts,
        raw_samples=raw_samples,
        options={"batch_limit": 5, "maxiter": 200},
    )
    return unnormalize(X_new_fullD_norm.detach(), bounds)


def safe_fit_gp_model(mll, train_X, train_Y):
    """
    Fit the GP model safely, falling back to Adam optimizer if standard fitting fails.

    Parameters
    ----------
    mll : MarginalLogLikelihood
        Marginal Log Likelihood object from GPyTorch.
    train_X : torch.Tensor
        Training inputs (normalized).
    train_Y : torch.Tensor
        Training targets (unnormalized).
    """
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


class VanillaBOStrategy(BaseStrategy):
    """
    Vanilla Bayesian Optimization strategy using Log Expected Improvement.

    This strategy uses standard GP fitting with qLogExpectedImprovement to suggest new candidates.
    """

    def initialize(self, X_init, Y_init, **kwargs):
        """
        Initialize the strategy with historical data.

        Parameters
        ----------
        X_init : torch.Tensor
            Initial input points.
        Y_init : torch.Tensor
            Initial observed objective values.
        kwargs : dict
            Additional keyword arguments (e.g., paths or context info).
        """
        pass  # No internal state needed for Vanilla BO

    def suggest(self, X_all_fullD_norm, Y_all_real, kernel, epoch, seed):
        """
        Suggest new candidates using a fitted GP model and acquisition function.

        Parameters
        ----------
        X_all_fullD_norm : torch.Tensor
            Normalized input history.
        Y_all_real : torch.Tensor
            Observed objective values.
        kernel : str
            Kernel type for the GP model (e.g., 'matern-1.5', 'matern-2.5', 'rbf').
        epoch : int
            Current optimization epoch.
        seed : int
            Random seed for reproducibility.

        Returns
        -------
        torch.Tensor
            New candidate points to evaluate (real scale).
        """
        best_f = Y_all_real.max()

        gp_model = initialize_model("vanillabo", X_all_fullD_norm, Y_all_real, kernel=kernel)
        mll = ExactMarginalLogLikelihood(gp_model.likelihood, gp_model)

        with max_cholesky_size(self.params["cholesky_limit"]):
            safe_fit_gp_model(mll, X_all_fullD_norm, Y_all_real)

            acq = qLogExpectedImprovement(
                model=gp_model,
                best_f=best_f,
                sampler=StochasticSampler(sample_shape=torch.Size([self.params["bo_sample_shape"]])),
            )

        X_new_fullD_real = optimize_acqf_and_create_candidate(
            acq_func=acq,
            bounds=self.bounds,
            device=self.device,
            dtype=self.dtype,
            batch_size=self.params["bo_batch_size"],
            num_restarts=self.params["bo_num_restarts"],
            raw_samples=self.params["bo_raw_samples"],
        )

        return X_new_fullD_real
