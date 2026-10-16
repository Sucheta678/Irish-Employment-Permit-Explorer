import { Link } from "react-router-dom";

import type { Company } from "../types";

interface ResultsTableProps {
  companies: Company[];
}

function ResultsTable({ companies }: ResultsTableProps) {
  if (companies.length === 0) {
    return <p>No companies found.</p>;
  }

  return (
    <div className="results-table-wrapper">
      <table className="results-table">
        <thead>
          <tr>
            <th>Company</th>
            <th>Sector</th>
            <th>Company Size</th>
            <th></th>
          </tr>
        </thead>

        <tbody>
          {companies.map((company) => (
            <tr key={company.id}>
              <td>{company.name}</td>

              <td>
                {company.enrichment?.sector ?? "Unknown"}
              </td>

              <td>
                {company.enrichment?.company_size ?? "Unknown"}
              </td>

              <td>
                <Link to={`/company/${company.id}`}>
                  View
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ResultsTable;