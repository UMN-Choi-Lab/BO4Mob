# Third-party imports
import random

import numpy as np
import torch


def set_seed(seed):
    """
    Set random seed across random, numpy, and PyTorch for reproducibility.

    Parameters
    ----------
    seed : int
        Random seed value to ensure reproducible results across libraries.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
