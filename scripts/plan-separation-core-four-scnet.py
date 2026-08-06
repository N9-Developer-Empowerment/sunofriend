#!/usr/bin/env python3
"""Print the public opt-in, no-write SCNet-large evidence/setup plan."""

import json

from sunofriend.separation_scnet_candidate import scnet_candidate_plan


if __name__ == "__main__":
    print(json.dumps(scnet_candidate_plan(), indent=2, sort_keys=True))
