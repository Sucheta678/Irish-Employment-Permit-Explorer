from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.company import CompanyListOut, CompanyOut, FilterOptions
from app.services import company_service

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyListOut)
def list_companies(
    search: str | None = Query(None, min_length=1, max_length=100),
    sector: str | None = Query(None, max_length=100),
    size: str | None = Query(None, max_length=50),
    sort_by: Literal["name", "permits"] = "permits",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return company_service.search_companies(
        db, search, sector, size, sort_by, order, page, page_size
    )


# must be declared before "/{company_id}"
@router.get("/filters", response_model=FilterOptions)
def filter_options(db: Session = Depends(get_db)):
    return company_service.get_filter_options(db)


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = company_service.get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company