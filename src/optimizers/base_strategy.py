# Standard library imports
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    """
    Abstract base class for all optimization strategies.

    All custom strategies must implement `initialize` and `suggest` methods
    to manage internal state and propose new candidate solutions.
    """

    def __init__(self, params, config, bounds, device, dtype):
        self.params = params
        self.config = config
        self.bounds = bounds
        self.device = device
        self.dtype = dtype

    @abstractmethod
    def initialize(self, X_init, Y_init):
        """Prepare internal state from initial data."""
        pass

    @abstractmethod
    def suggest(self, X_all_fullD_norm, Y_all_real, kernel, epoch, seed):
        """Suggest new candidates. Returns X_new_fullD_real (np.ndarray)."""
        pass
