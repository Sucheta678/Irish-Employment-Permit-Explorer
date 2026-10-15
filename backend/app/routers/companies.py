from fastapi import APIRouter

from app.schemas.company import CompanyResponse


router = APIRouter(prefix="/companies", tags=["companies"])


mock_companies = [
    CompanyResponse(
        id=1,
        name="Example Technology Ltd",
        year=2026,
        occupation="Software Developer",
        enrichment={
            "sector": "Technology",
            "company_size": "Large",
            "source": "Company website",
            "researched_at": "2026-10-10",
        },
    ),
    CompanyResponse(
        id=2,
        name="Example Healthcare Ltd",
        year=2025,
        occupation="Data Analyst",
        enrichment={
            "sector": "Healthcare",
            "company_size": "Medium",
            "source": "Company website",
            "researched_at": "2026-10-10",
        },
    ),
    CompanyResponse(
        id=3,
        name="Example Finance Ltd",
        year=2026,
        occupation="Data Analyst",
        enrichment={
            "sector": "Finance",
            "company_size": "Large",
            "source": "Company website",
            "researched_at": "2026-10-10",
        },
    ),
    CompanyResponse(
        id=4,
        name="Example Engineering Ltd",
        year=2024,
        occupation="Engineer",
        enrichment={
            "sector": "Engineering",
            "company_size": None,
            "source": None,
            "researched_at": None,
        },
    ),
]


@router.get("", response_model=list[CompanyResponse])
def get_companies():
    return mock_companies