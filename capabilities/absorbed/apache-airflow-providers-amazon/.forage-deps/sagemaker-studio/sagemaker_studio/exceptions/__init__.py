from botocore.exceptions import ClientError


class AWSClientException(ClientError):
    """
    An exception class that translates a ClientError from botocore to reveal
    ResponseMetadata when the stack trace is printed. Maintains backward compatibility with
    botocore.exceptions.ClientError
    """

    def __init__(self, client_error: ClientError):
        self._client_error = client_error
        self.response = client_error.response
        self._response_metadata = self.response.get("ResponseMetadata", {})
        super().__init__(self.response, client_error.operation_name)

    def __str__(self):
        return f"{str(self._client_error)}\nResponseMetadata: {self._response_metadata}"
