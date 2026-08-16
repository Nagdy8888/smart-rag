"""Next-call-only tool binding using pinned langchain-core + LangGraph.

Current LangChain docs use ``wrap_model_call`` plus
``request.override(tools=...)`` on ``langchain.agents`` middleware
(https://docs.langchain.com/oss/python/langchain/tools#dynamic-tool-selection).
That API lives in the unpinned ``langchain`` distribution. This module is
the pin-compatible equivalent: ``BaseChatModel.bind_tools`` when
implemented, otherwise ``Runnable.bind(tools=...)`` from
``langchain-core==1.5.4``. Both return a new runnable for one invocation
and leave the original model unbound.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables.base import Runnable
from langchain_core.tools.base import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

BoundChat = Runnable[Any, Any]


def selected_tool_schemas(
    tools: Sequence[BaseTool | dict[str, object]],
) -> list[dict[str, object]]:
    """Convert selected tools to OpenAI tool schema dicts.

    Args:
        tools: LangChain tools or already-formatted schema dicts.

    Returns:
        Schema mappings for one model bind.
    """

    schemas: list[dict[str, object]] = []
    for item in tools:
        if isinstance(item, dict):
            schemas.append(dict(item))
            continue
        converted = cast(dict[str, object], convert_to_openai_tool(item))
        schemas.append(converted)
    return schemas


def bound_tool_names(runnable: object) -> tuple[str, ...]:
    """Read tool function names bound on a runnable, if any.

    Args:
        runnable: Chat model or ``bind``/``bind_tools`` result.

    Returns:
        Tool names. Empty when the runnable has no tools kwargs.
    """

    kwargs_raw = getattr(runnable, "kwargs", None)
    if not isinstance(kwargs_raw, dict):
        return ()
    kwargs_typed = cast(dict[str, object], kwargs_raw)
    tools_raw = kwargs_typed.get("tools")
    if not isinstance(tools_raw, list):
        return ()
    names: list[str] = []
    for raw_item in cast(list[object], tools_raw):
        if not isinstance(raw_item, dict):
            name = getattr(raw_item, "name", None)
            if isinstance(name, str) and name:
                names.append(name)
            continue
        item = cast(dict[str, object], raw_item)
        function = item.get("function")
        if isinstance(function, dict):
            function_typed = cast(dict[str, object], function)
            fname = function_typed.get("name")
            if isinstance(fname, str) and fname:
                names.append(fname)
                continue
        tname = item.get("name")
        if isinstance(tname, str) and tname:
            names.append(tname)
    return tuple(names)


def bind_selected_tools_next_call(
    model: BaseChatModel,
    tools: Sequence[BaseTool | dict[str, object]],
) -> BoundChat:
    """Bind ``tools`` for the next model invocation only.

    The original ``model`` is not mutated. A later ``model.invoke`` or a
    new bind with a different set does not receive the previous schemas.

    Args:
        model: Pinned langchain-core chat model.
        tools: Selected tools or schema dicts. Unselected tools omitted.

    Returns:
        Runnable whose kwargs include only the selected tool schemas.
    """

    schemas = selected_tool_schemas(tools)
    bind_tools = getattr(model, "bind_tools", None)
    if callable(bind_tools):
        try:
            return cast(BoundChat, bind_tools(list(tools)))
        except NotImplementedError:
            pass
    return cast(BoundChat, model.bind(tools=schemas))
