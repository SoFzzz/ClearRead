"""The one error type routes raise; handlers answer ``{"error": code}``."""


class ApiError(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
