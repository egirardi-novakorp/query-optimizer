from pydantic import BaseModel
from typing import Optional, Any

class AnalyzeRequest(BaseModel):
    query: str
    ddl: str | None = None
    explain_plan: str | None = None
    context: str | None = None

class RuleFinding(BaseModel):
    rule_id: str           # "R01"
    rule_name: str         # "CTE innecesaria"
    severity: str          # "critical", "warning", "info"
    description: str
    location: str          # "CTE 'datos_base', linea 5"
    suggestion: str
    code_before: str = ""
    code_after: str = ""

class AnalyzeResponse(BaseModel):
    original_query: str
    optimized_query: str | None = None
    findings: list[RuleFinding]
    summary: dict          # {"critical": 2, "warning": 3, "info": 1}
    llm_analysis: str | None = None
    explain_analysis: str | None = None


class ChatRequest(BaseModel):
    message: str
    ddl: str | None = None
    explain_plan: str | None = None
    context: str | None = None
    history: list[dict] = []  # [{"role": "user", "content": "..."}, ...]
    last_analysis: Optional[dict] = None  # Último análisis para contexto


class ChatResponse(BaseModel):
    type: str  # "analysis" o "chat"
    analysis: Optional[AnalyzeResponse] = None  # si type == "analysis"
    message: Optional[str] = None  # si type == "chat"
