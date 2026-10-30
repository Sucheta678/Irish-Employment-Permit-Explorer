import math
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company

SORT_COLUMNS = {
    "name": Company.company_name,
    "permits": Company.permit_count,
}


def search_companies(
    db: Session,
    search: str | None,
    sector: str | None,
    size: str | None,
    sort_by: str,
    order: str,
    page: int,
    page_size: int,
) -> dict:
    filters = []
    if search:
        filters.append(Company.company_name.like(f"%{search.strip()}%"))
    if sector:
        filters.append(Company.sector == sector)
    if size:
        filters.append(Company.size_of_company == size)

    total = db.scalar(select(func.count()).select_from(Company).where(*filters)) or 0

    col = SORT_COLUMNS[sort_by]
    ordering = col.desc() if order == "desc" else col.asc()

    items = db.scalars(
        select(Company)
        .where(*filters)
        .order_by(ordering, Company.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def get_company_by_id(db: Session, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def get_filter_options(db: Session) -> dict:
    sectors = db.scalars(
        select(Company.sector)
        .where(Company.sector.is_not(None))
        .distinct()
        .order_by(Company.sector)
    ).all()
    sizes = db.scalars(
        select(Company.size_of_company)
        .where(Company.size_of_company.is_not(None))
        .distinct()
    ).all()
    return {"sectors": sectors, "sizes": sizes}