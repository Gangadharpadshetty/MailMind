"""Domain-specific exceptions — SRP: each exception has one meaning."""


class MailMindException(Exception):
    """Base exception for MailMind."""


class SessionNotFoundError(MailMindException):
    def __init__(self, session_id: str):
        super().__init__(f"Session '{session_id}' not found. Call POST /start_session first.")
        self.session_id = session_id


class ThreadNotFoundError(MailMindException):
    def __init__(self, thread_id: str):
        super().__init__(f"Thread '{thread_id}' not found in the index.")
        self.thread_id = thread_id


class IndexNotReadyError(MailMindException):
    def __init__(self):
        super().__init__("Index is not built yet. Run `python ingest.py` first.")


class ProviderNotFoundError(MailMindException):
    def __init__(self, provider_id: str):
        super().__init__(f"LLM provider '{provider_id}' is not registered.")
        self.provider_id = provider_id


class IngestError(MailMindException):
    """Raised when email parsing / indexing fails."""
