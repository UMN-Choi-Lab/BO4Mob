# Third-party imports
from botorch.models import SingleTaskGP
from botorch.models.fully_bayesian import SaasFullyBayesianSingleTaskGP
from botorch.models.transforms import Standardize
from gpytorch.constraints import Interval
from gpytorch.kernels import MaternKernel, ScaleKernel
from gpytorch.likelihoods import GaussianLikelihood


def initialize_vanillabo_model(train_X, train_Y):
    """Initialize a standard GP model with Matern kernel for Vanilla BO."""
    dim = train_X.size(-1)
    likelihood = GaussianLikelihood(noise_constraint=Interval(1e-8, 1e-3))
    covar_module = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=dim, lengthscale_constraint=Interval(0.005, 4.0)))
    model = SingleTaskGP(
        train_X,
        train_Y,
        covar_module=covar_module,
        likelihood=likelihood,
        outcome_transform=Standardize(m=1),
    )
    return model


def initialize_saasbo_model(train_X, train_Y):
    """Initialize a fully Bayesian SAASBO model using SaasFullyBayesianSingleTaskGP."""
    model = SaasFullyBayesianSingleTaskGP(train_X, train_Y, outcome_transform=Standardize(m=1))
    return model


def initialize_turbo_model(train_X, train_Y):
    """Initialize a standard GP model with Matern kernel for use in TurBO."""
    dim = train_X.size(-1)
    likelihood = GaussianLikelihood(noise_constraint=Interval(1e-8, 1e-3))
    covar_module = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=dim, lengthscale_constraint=Interval(0.005, 4.0)))
    model = SingleTaskGP(
        train_X,
        train_Y,
        covar_module=covar_module,
        likelihood=likelihood,
        outcome_transform=Standardize(m=1),
    )
    return model


def initialize_model(model_name: str, train_X, train_Y):
    """Select and initialize a GP model based on the given model name."""
    if model_name == "vanillabo":
        return initialize_vanillabo_model(train_X, train_Y)
    elif model_name == "saasbo":
        return initialize_saasbo_model(train_X, train_Y)
    elif model_name == "turbo":
        return initialize_turbo_model(train_X, train_Y)
    else:
        raise ValueError(f"Unknown model name: {model_name}")
