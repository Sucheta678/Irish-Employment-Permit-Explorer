from pydantic import BaseModel


class CompanyEnrichment(BaseModel):
    sector: str | None = None
    company_size: str | None = None
    source: str | None = None
    researched_at: str | None = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    year: int
    occupation: str
    enrichment: CompanyEnrichment | None = None