class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""


class InvalidInputError(Exception):
    """Raised when a request cannot be processed."""

    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.status_code = status_code
