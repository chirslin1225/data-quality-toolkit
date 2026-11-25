"""dqkit — cost-weighted data quality scoring for tabular data."""

__version__ = "0.2.0"

from .checks import CHECKS, Finding, run_checks  # noqa: F401
from .score import DEFAULT_COSTS, score  # noqa: F401
from .uncertainty import estimate_uncertainty  # noqa: F401
