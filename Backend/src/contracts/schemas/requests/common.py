"""Request parameters shared by every list endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=200)
