import type { Company } from "../types";

interface CompanyCardProps {
  company: Company;
}

function CompanyCard({ company }: CompanyCardProps) {
  return (
    <article className="company-card">
      <h3>{company.name}</h3>

      <p>
        Sector: {company.enrichment?.sector ?? "Unknown"}
      </p>

      <p>
        Company size: {company.enrichment?.company_size ?? "Unknown"}
      </p>
    </article>
  );
}

export default CompanyCard;