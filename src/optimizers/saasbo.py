# Third-party imports
import torch
from botorch.acquisition import qExpectedImprovement
from botorch.fit import fit_fully_bayesian_model_nuts
from botorch.optim import optimize_acqf
from botorch.utils.transforms import unnormalize

from models.gp_models import initialize_model

# Local application imports
from optimizers.base_strategy import BaseStrategy


def optimize_acqf_and_create_candidate(acq_func, bounds, device, dtype, batch_size, num_restarts, raw_samples):
    """Optimize the acquisition function and return new candidate points (saasbo version)."""
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


class SAASBOStrategy(BaseStrategy):
    """
    Strategy implementing SAASBO (Sparse Axis-Aligned Subspace BO) using fully Bayesian models.

    This strategy fits a SAASBO GP model using NUTS sampling and uses qEI as the acquisition function.
    """

    def initialize(self, X_init, Y_init, **kwargs):
        """Initialize the strategy with initial data."""
        pass  # No internal state needed for SAASBO

    def suggest(self, X_all_fullD_norm, Y_all_real, kernel, epoch, seed):
        """
        Suggest new candidates using the SAASBO acquisition function.

        Parameters
        ----------
        X_all_fullD_norm : torch.Tensor
            Normalized historical input data.
        Y_all_real : torch.Tensor
            Observed objective values (negated loss).
        epoch : int
            Current epoch index.
        seed : int
            Random seed for reproducibility.

        Returns
        -------
        torch.Tensor
            Suggested candidate(s) for the next evaluation batch.
        """
        best_f = Y_all_real.max()

        # Initialize SAASBO model
        gp_model = initialize_model("saasbo", X_all_fullD_norm, Y_all_real, kernel=kernel)

        # Fit model using NUTS sampler
        fit_fully_bayesian_model_nuts(
            model=gp_model,
            warmup_steps=self.params["bo_warmup_steps"],
            num_samples=self.params["bo_num_samples"],
            thinning=self.params["bo_thinning"],
            disable_progbar=True,
        )
        print("Median lengthscales:", gp_model.median_lengthscale.detach())

        # Define acquisition function
        acq = qExpectedImprovement(model=gp_model, best_f=best_f)

        # Optimize acquisition function
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
