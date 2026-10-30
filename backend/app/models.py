from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Company(Base):
    __tablename__ = "employment_permit_2026"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    permit_count: Mapped[int] = mapped_column(Integer, default=0)
    sector: Mapped[str | None] = mapped_column(String(100), index=True)
    size_of_company: Mapped[str | None] = mapped_column(String(50), index=True)