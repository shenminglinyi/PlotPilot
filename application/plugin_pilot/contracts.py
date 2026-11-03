"""Host-owned contracts. Plugin declarations cannot expand these capabilities."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

HOST_API = "0.1"
ARTIFACT_TYPE = "character_card_patch@1"
FIELDS = ("appearance", "personality", "core_motivation")
MAX_INPUT_TOKENS = 16000
MAX_OUTPUT_TOKENS = 2048
MAX_INPUT_CHARS = 8000
MAX_OUTPUT_BYTES = 12000
TIMEOUT_SECONDS = 45
MAX_CALLS = 1
FieldName = Literal["appearance", "personality", "core_motivation"]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=150,
                                             pattern=r"^[A-Za-z0-9_:.\-]+$")]
Value = Annotated[str, StringConstraints(min_length=1, max_length=600)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def explicit_boolean_consent(cls, value):
        if isinstance(value, dict):
            for key in ("consent", "confirm"):
                if key in value and value[key] is not True:
                    raise ValueError("Explicit boolean confirmation is required")
        return value


class Evidence(StrictModel):
    field: FieldName
    quote: Annotated[str, StringConstraints(min_length=1, max_length=400)]


class CharacterPatch(StrictModel):
    artifact_type: Literal["character_card_patch@1"]
    patch: dict[FieldName, Value] = Field(min_length=1, max_length=3)
    evidence: list[Evidence] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def evidence_matches_fields(self):
        if {e.field for e in self.evidence} != set(self.patch):
            raise ValueError("Every changed field needs evidence; no unrelated evidence")
        if any(not value.strip() for value in self.patch.values()):
            raise ValueError("Patch strings cannot be blank")
        if any(not evidence.quote.strip() for evidence in self.evidence):
            raise ValueError("Evidence quote cannot be blank")
        return self


class RunRequest(StrictModel):
    plugin_id: Identifier
    project_id: Identifier
    chapter_id: Identifier
    character_id: Identifier
    model_signature: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    consent: Literal[True]


class AdoptRequest(StrictModel):
    project_id: Identifier
    command_id: Annotated[str, StringConstraints(min_length=8, max_length=100,
                                                pattern=r"^[A-Za-z0-9_-]+$")]
    confirm: Literal[True]


class PilotError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status
