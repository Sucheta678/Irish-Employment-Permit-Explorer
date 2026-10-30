import { useEffect, useState } from "react";

import SearchBar from "../components/SearchBar";
import FilterPanel from "../components/FilterPanel";
import ResultsTable from "../components/ResultsTable";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import { getCompanies, getFilterOptions } from "../services/api";

import type { CompanyList, FilterOptions } from "../types";

const PAGE_SIZE = 20;
const SEARCH_DELAY_MS = 300;

interface Query {
  search: string;
  sector: string;
  companySize: string;
  page: number;
}

type Result =
  | { query: Query; data: CompanyList }
  | { query: Query; error: string };

function Search() {
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState<Query>({
    search: "",
    sector: "",
    companySize: "",
    page: 1,
  });
  const [result, setResult] = useState<Result | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    sectors: [],
    sizes: [],
  });

  useEffect(() => {
    getFilterOptions()
      .then(setFilterOptions)
      .catch(() => {
        // The filters stay empty; the results request reports the error.
      });
  }, []);

  // Wait until the user stops typing before searching.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery((current) =>
        current.search === searchInput.trim()
          ? current
          : { ...current, search: searchInput.trim(), page: 1 },
      );
    }, SEARCH_DELAY_MS);

    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    let cancelled = false;

    getCompanies({
      search: query.search,
      sector: query.sector,
      size: query.companySize,
      page: query.page,
      pageSize: PAGE_SIZE,
    })
      .then((data) => {
        if (!cancelled) setResult({ query, data });
      })
      .catch(() => {
        if (!cancelled) {
          setResult({ query, error: "Failed to load companies." });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [query]);

  function handleSearch() {
    setQuery((current) => ({ ...current, search: searchInput.trim(), page: 1 }));
  }

  const loading = result === null || result.query !== query;

  return (
    <section>
      <h1>Search Companies</h1>

      <SearchBar
        value={searchInput}
        onChange={setSearchInput}
        onSearch={handleSearch}
      />

      <FilterPanel
        options={filterOptions}
        sector={query.sector}
        companySize={query.companySize}
        onSectorChange={(sector) => setQuery({ ...query, sector, page: 1 })}
        onCompanySizeChange={(companySize) =>
          setQuery({ ...query, companySize, page: 1 })
        }
      />

      <h2>Results</h2>

      {loading && <LoadingState />}

      {!loading && "error" in result && <ErrorState message={result.error} />}

      {!loading && "data" in result && (
        <>
          <p>
            {result.data.total.toLocaleString()}{" "}
            {result.data.total === 1 ? "company" : "companies"} found
          </p>

          <ResultsTable companies={result.data.items} />

          {result.data.total_pages > 1 && (
            <nav className="pagination" aria-label="Results pages">
              <button
                type="button"
                disabled={query.page <= 1}
                onClick={() => setQuery({ ...query, page: query.page - 1 })}
              >
                Previous
              </button>

              <span>
                Page {query.page} of {result.data.total_pages}
              </span>

              <button
                type="button"
                disabled={query.page >= result.data.total_pages}
                onClick={() => setQuery({ ...query, page: query.page + 1 })}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

export default Search;
