"""Recording LangSmith client used by query and ingest tracing tests."""

from __future__ import annotations

from typing import Any


class RecordingLangSmithClient:
    """In-memory LangSmith client that never opens a network connection."""

    def __init__(self) -> None:
        """Initialize empty create/update buffers."""

        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    def create_run(
        self,
        name: str,
        inputs: dict[str, Any],
        run_type: str = "chain",
        **kwargs: Any,
    ) -> None:
        """Record one create_run payload.

        Args:
            name: Run name.
            inputs: Run inputs after process_inputs.
            run_type: LangSmith run type.
            **kwargs: Additional SDK fields including outputs.
        """

        self.created.append(
            {
                "name": name,
                "inputs": inputs,
                "run_type": run_type,
                "kwargs": kwargs,
            }
        )

    def update_run(self, run_id: object, **kwargs: Any) -> None:
        """Record one update_run payload.

        Args:
            run_id: Run identifier.
            **kwargs: Output/end fields.
        """

        self.updated.append({"run_id": run_id, **kwargs})

    def __getattr__(self, name: str) -> Any:
        """Ignore unused Client methods used by RunTree internals.

        Args:
            name: Attribute requested by the SDK.

        Returns:
            A no-op callable.
        """

        def _ignored(*args: Any, **kwargs: Any) -> None:
            """Swallow unused SDK calls.

            Args:
                *args: Positional SDK arguments.
                **kwargs: Keyword SDK arguments.
            """

            return None

        return _ignored
