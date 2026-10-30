import type { Company } from "../types";

interface CompanyCardProps {
  company: Company;
}

function CompanyCard({ company }: CompanyCardProps) {
  return (
    <article className="company-card">
      <h3>{company.company_name}</h3>

      <p>
        Sector: {company.sector ?? "Unknown"}
      </p>

      <p>
        Company size: {company.size_of_company ?? "Unknown"}
      </p>

      <p>
        Permits (2026): {company.permit_count}
      </p>
    </article>
  );
}

export default CompanyCard;