import type { CompanyEnrichment } from "./companyEnrichment";

export interface Company {
id: number;
name: string;
year: number;
occupation: string;
enrichment: CompanyEnrichment | null;
}