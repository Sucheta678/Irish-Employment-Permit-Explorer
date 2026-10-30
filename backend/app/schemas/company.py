from pydantic import BaseModel, ConfigDict


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    permit_count: int
    sector: str | None
    size_of_company: str | None


class CompanyListOut(BaseModel):
    items: list[CompanyOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class FilterOptions(BaseModel):
    sectors: list[str]
    sizes: list[str]