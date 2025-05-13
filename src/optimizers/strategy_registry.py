# Local application imports
from optimizers.saasbo import SAASBOStrategy
from optimizers.spsa import SPSAStrategy
from optimizers.turbo import TurboStrategy
from optimizers.vanillabo import VanillaBOStrategy

strategy_registery = {
    "spsa": SPSAStrategy,
    "vanillabo": VanillaBOStrategy,
    "saasbo": SAASBOStrategy,
    "turbo": TurboStrategy,
}
