import type { Company, CompanyList, FilterOptions } from "../types";

const API_BASE_URL = "http://127.0.0.1:8000";

export interface CompanySearchParams {
  search?: string;
  sector?: string;
  size?: string;
  page?: number;
  pageSize?: number;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${path} (${response.status})`);
  }

  return response.json();
}

export function getCompanies(params: CompanySearchParams = {}): Promise<CompanyList> {
  const query = new URLSearchParams();

  if (params.search) query.set("search", params.search);
  if (params.sector) query.set("sector", params.sector);
  if (params.size) query.set("size", params.size);
  if (params.page) query.set("page", String(params.page));
  if (params.pageSize) query.set("page_size", String(params.pageSize));

  return getJson<CompanyList>(`/companies?${query}`);
}

export function getCompany(id: number): Promise<Company> {
  return getJson<Company>(`/companies/${id}`);
}

export function getFilterOptions(): Promise<FilterOptions> {
  return getJson<FilterOptions>("/companies/filters");
}
