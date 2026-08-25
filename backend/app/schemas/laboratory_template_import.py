"""Response schemas for Laboratory Template Import/Export (bulk Excel
maintenance). See `app/services/laboratory_template_import_export.py`'s
module docstring for the workbook format these mirror."""

from pydantic import BaseModel


class ImportIssueRead(BaseModel):
    severity: str  # "error" | "warning"
    sheet: str
    row: int
    template: str | None = None
    parameter: str | None = None
    reason: str


class TemplateParameterDiffRead(BaseModel):
    """Per-template parameter synchronization preview - the `+`/`~`/`-`
    breakdown the spec explicitly asked to see before any commit."""

    added: list[str] = []
    changed: list[str] = []
    removed: list[str] = []
    unchanged: list[str] = []


class TemplateDiffRead(BaseModel):
    template_id: str | None = None
    test_name: str
    action: str  # "create" | "update"
    parameters: TemplateParameterDiffRead


class ImportPreviewRead(BaseModel):
    template_count: int
    parameter_count: int
    new_template_count: int
    updated_template_count: int
    errors: list[ImportIssueRead]
    warnings: list[ImportIssueRead]
    diffs: list[TemplateDiffRead]
    can_commit: bool


class ImportCommitRead(BaseModel):
    created_template_count: int
    updated_template_count: int
    parameter_count: int
    template_names: list[str]
