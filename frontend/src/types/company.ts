// Mirrors the backend schemas in backend/app/schemas/company.py.

export interface Company {
  id: number;
  company_name: string;
  permit_count: number;
  sector: string | null;
  size_of_company: string | null;
}

export interface CompanyList {
  items: Company[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface FilterOptions {
  sectors: string[];
  sizes: string[];
}
