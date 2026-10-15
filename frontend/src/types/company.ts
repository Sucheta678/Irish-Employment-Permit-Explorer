import type { CompanyEnrichment } from "./companyEnrichment";

export interface Company {
  id: number;
  name: string;
  enrichment: CompanyEnrichment | null;
}