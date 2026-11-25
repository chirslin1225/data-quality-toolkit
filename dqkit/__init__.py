"""dqkit — cost-weighted data quality scoring for tabular data."""

__version__ = "0.1.0"

from .checks import CHECKS, PLANNED, Finding, run_checks  # noqa: F401
from .score import DEFAULT_COSTS, score  # noqa: F401
