"""Chronological rule-strategy evaluation; no automatic profitable-strategy claim."""

from quant_core.validation.contracts import CampaignSpec, Capability, Criteria, Qualification
from quant_core.validation.temporal import LabelInterval, Period, past_training_samples

__all__ = ["CampaignSpec", "Capability", "Criteria", "Qualification", "LabelInterval", "Period",
           "past_training_samples"]
