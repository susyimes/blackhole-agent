from typing import Dict


class GitCodeConnectionsClient:
    def __init__(self, connection_arn: str):
        self.connection_arn = connection_arn

    def get_clone_url(self, repository_id: str) -> Dict[str, str]:
        parsed_arn = self._parse_arn(self.connection_arn)
        resource_parts = parsed_arn["resource"].split("/")
        if len(resource_parts) != 2 or resource_parts[0] != "connection":
            raise ValueError(f"Invalid resource format in ARN: {self.connection_arn}")
        connection_uuid = resource_parts[1]
        return {
            "cloneUrl": f"https://codeconnections.{parsed_arn['region']}.amazonaws.com/git-http/{parsed_arn['account_id']}/{parsed_arn['region']}/{connection_uuid}/{repository_id}.git"
        }

    def _parse_arn(self, arn: str):
        parts = arn.split(":")
        if len(parts) < 6:
            raise ValueError(f"Invalid ARN format: {arn}")

        return {
            "arn": parts[0],
            "partition": parts[1],
            "service": parts[2],
            "region": parts[3],
            "account_id": parts[4],
            "resource": ":".join(parts[5:]),
        }
