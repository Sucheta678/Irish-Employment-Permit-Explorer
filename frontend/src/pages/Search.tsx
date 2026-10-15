import { useEffect, useMemo, useState } from "react";

import SearchBar from "../components/SearchBar";
import FilterPanel from "../components/FilterPanel";
import ResultsTable from "../components/ResultsTable";
import { getCompanies } from "../services/api";

import type { Company } from "../types";

function Search() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [search, setSearch] = useState("");
  const [year, setYear] = useState("");
  const [sector, setSector] = useState("");
  const [occupation, setOccupation] = useState("");
  const [companySize, setCompanySize] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadCompanies() {
      try {
        const data = await getCompanies();
        setCompanies(data);
      } catch {
        setError("Failed to load companies.");
      } finally {
        setLoading(false);
      }
    }

    loadCompanies();
  }, []);

  const filteredCompanies = useMemo(() => {
    return companies.filter((company) => {
      const matchesSearch =
        company.name.toLowerCase().includes(search.toLowerCase());

      const matchesYear =
        year === "" || company.year === Number(year);

      const matchesSector =
        sector === "" ||
        company.enrichment?.sector === sector;

      const matchesOccupation =
        occupation === "" ||
        company.occupation === occupation;

      const matchesCompanySize =
        companySize === "" ||
        company.enrichment?.company_size === companySize;

      return (
        matchesSearch &&
        matchesYear &&
        matchesSector &&
        matchesOccupation &&
        matchesCompanySize
      );
    });
  }, [companies, search, year, sector, occupation, companySize]);

  function handleSearch() {
    console.log("Search filters:", {
      search,
      year,
      sector,
      occupation,
      companySize,
    });
  }

  if (loading) {
    return <p>Loading companies...</p>;
  }

  if (error) {
    return <p>{error}</p>;
  }

  return (
    <section>
      <h1>Search Companies</h1>

      <SearchBar
        value={search}
        onChange={setSearch}
        onSearch={handleSearch}
      />

      <FilterPanel
        year={year}
        sector={sector}
        occupation={occupation}
        companySize={companySize}
        onYearChange={setYear}
        onSectorChange={setSector}
        onOccupationChange={setOccupation}
        onCompanySizeChange={setCompanySize}
      />

      <h2>Results</h2>

      <p>
        {filteredCompanies.length}{" "}
        {filteredCompanies.length === 1 ? "company" : "companies"} found
      </p>

      <ResultsTable companies={filteredCompanies} />
    </section>
  );
}

export default Search;