from __future__ import annotations

import numexpr as ne
import numpy as np


def evaluate_formula(
    formula: str,
    variables: dict[str, np.ndarray],
) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return ne.evaluate(formula, local_dict=variables)
