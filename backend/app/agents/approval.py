"""LangChain tool proxy that requests a human decision before execution."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field

APPROVAL_REJECTED_PREFIX = "error: approval rejected:"


class ApprovalDenied(Exception):
    """A mutating tool was rejected, expired, or cancelled."""


class ApprovalTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    wrapped: Any = Field(exclude=True)
    approval_hook: Any = Field(exclude=True)

    async def _arun(self, **kwargs: Any) -> str:
        try:
            await self.approval_hook(self.name, kwargs)
        except ApprovalDenied as exc:
            return f"{APPROVAL_REJECTED_PREFIX} {exc}"
        return await self.wrapped.ainvoke(kwargs)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("approval tools are async only")

    @classmethod
    def wrap(cls, tool: BaseTool, hook: Any) -> ApprovalTool:
        return cls(
            name=tool.name,
            description=tool.description or "",
            args_schema=tool.args_schema,
            wrapped=tool,
            approval_hook=hook,
        )
