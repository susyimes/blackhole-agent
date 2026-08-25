from typing import Dict, List


def find_default_tooling_environment(environments: List[Dict]):
    return min(
        [env for env in environments if env["deploymentOrder"] is not None],
        key=lambda env: env["deploymentOrder"],
        default=None,
    )
