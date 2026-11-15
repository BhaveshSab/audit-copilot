from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Investigate(Strict):
    cycle_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    question: str = Field(
        default="Investigate the recorded audit result against asset custody and policy.",
        max_length=2000,
    )


class Clause(Strict):
    id: str
    title: str
    text: str
    source: str
    version: str = "demo-v1"


class Evidence(Strict):
    id: str
    tool: str
    data: dict


class Fact(Strict):
    evidence_id: str
    quote: str = Field(min_length=1, max_length=2000)


class EvidenceReport(Strict):
    facts: list[Fact] = Field(max_length=24)
    summary: str = Field(max_length=4000)


class PolicyRef(Strict):
    clause_id: str
    quote: str = Field(min_length=1, max_length=2000)


class PolicyReport(Strict):
    refs: list[PolicyRef] = Field(max_length=8)
    summary: str = Field(max_length=4000)


class Finding(Strict):
    category: Literal[
        "clean",
        "transferred",
        "maintenance",
        "disposed",
        "missing",
        "damaged",
        "duplicate_tag",
        "insufficient_evidence",
    ]
    result: Literal["VERIFIED", "MISSING", "DAMAGED"] | None
    cause: str = Field(max_length=3000)
    evidence_ids: list[str] = Field(max_length=24)
    policy_refs: list[PolicyRef] = Field(max_length=8)
    confidence: float = Field(ge=0, le=1)
    recommended_action: str = Field(max_length=2000)
    refused: bool = False

    @model_validator(mode="after")
    def grounded(self):
        if self.refused:
            if self.result is not None or self.category != "insufficient_evidence":
                raise ValueError("Refusals cannot propose an audit mark")
        elif (
            not self.evidence_ids
            or not self.policy_refs
            or self.result is None
            or self.category == "insufficient_evidence"
        ):
            raise ValueError(
                "Non-refused findings require evidence, policy and a result"
            )
        if not self.refused:
            expected = {
                "clean": "VERIFIED",
                "missing": "MISSING",
                "damaged": "DAMAGED",
            }.get(self.category)
            if expected and self.result != expected:
                raise ValueError("Finding category conflicts with proposed result")
        return self


class Review(Strict):
    action: Literal["approve", "reject"]
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A nonblank human review note is required")
        return value


class ToolArgs(Strict):
    cycle_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
