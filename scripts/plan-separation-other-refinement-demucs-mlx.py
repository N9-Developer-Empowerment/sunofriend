#!/usr/bin/env python3
"""Print the no-write six-source MLX Studio-challenger plan."""

import json

from sunofriend.separation_other_refinement_demucs_mlx_candidate import (
    demucs_mlx_other_refinement_candidate_plan,
)


if __name__ == "__main__":
    print(
        json.dumps(
            demucs_mlx_other_refinement_candidate_plan(),
            indent=2,
            sort_keys=True,
        )
    )
