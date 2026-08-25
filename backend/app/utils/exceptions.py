class FinanceControllerError(Exception):
    """Base exception for expected application errors."""


class DataValidationError(FinanceControllerError):
    """Raised when a source record cannot be validated."""
