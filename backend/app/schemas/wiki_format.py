"""Request and response models for a story's wiki format."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")[:32]
    if not slug:
        return "type"
    return slug if slug[0].isalpha() else f"type_{slug}"[:32]


class WikiSectionFlags(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: bool = True
    facts: bool = True
    relationships: bool = True
    aliases: bool = True
    appearances: bool = True
    threads: bool = True


class WikiFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=80)
    hint: str = Field(default="", max_length=200)

    @field_validator("key", mode="before")
    @classmethod
    def normalise_key(cls, value: object) -> str:
        return slugify(str(value or ""))

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("Field keys must be lowercase letters, numbers, or underscores.")
        return value

    @field_validator("label", mode="before")
    @classmethod
    def clean_label(cls, value: object) -> str:
        return str(value or "").strip()


class WikiEntryType(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    sections: WikiSectionFlags = Field(default_factory=WikiSectionFlags)
    fields: list[WikiFieldDefinition] = Field(default_factory=list, max_length=40)

    @field_validator("key", mode="before")
    @classmethod
    def normalise_key(cls, value: object) -> str:
        return slugify(str(value or ""))

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("Type keys must be lowercase letters, numbers, or underscores.")
        return value

    @field_validator("label", mode="before")
    @classmethod
    def clean_label(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def unique_fields(self) -> WikiEntryType:
        seen: set[str] = set()
        for item in self.fields:
            if item.key in seen:
                raise ValueError(f"Duplicate field key: {item.key}")
            seen.add(item.key)
        return self


class WikiFormat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: Literal[1] = 1
    types: list[WikiEntryType] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def unique_types(self) -> WikiFormat:
        seen: set[str] = set()
        for item in self.types:
            if item.key in seen:
                raise ValueError(f"Duplicate type key: {item.key}")
            seen.add(item.key)
        return self


class WikiFormatOut(WikiFormat):
    pass
