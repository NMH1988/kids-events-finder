"""The app's own input errors, whose messages are safe to show to the model and the parent."""


class AppInputError(ValueError):
    """A value is outside what the app accepts; the app wrote the message, never a service."""
