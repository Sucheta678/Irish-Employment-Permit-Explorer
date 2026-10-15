import { useMemo, useState } from "react";

import SearchBar from "../components/SearchBar";
import FilterPanel from "../components/FilterPanel";
import ResultsTable from "../components/ResultsTable";

import type { Company } from "../types";

interface MockCompany extends Company {
  year: number;
  occupation: string;
}

const mockCompanies: MockCompany[] = [
  {
    id: 1,
    name: "Example Technology Ltd",
    year: 2026,
    occupation: "Software Developer",
    enrichment: {
      sector: "Technology",
      companySize: "Large",
      source: "Company website",
      researchedAt: "2026-10-10",
    },
  },
  {
    id: 2,
    name: "Example Healthcare Ltd",
    year: 2025,
    occupation: "Data Analyst",
    enrichment: {
      sector: "Healthcare",
      companySize: "Medium",
      source: "Company website",
      researchedAt: "2026-10-10",
    },
  },
  {
    id: 3,
    name: "Example Finance Ltd",
    year: 2026,
    occupation: "Data Analyst",
    enrichment: {
      sector: "Finance",
      companySize: "Large",
      source: "Company website",
      researchedAt: "2026-10-10",
    },
  },
  {
    id: 4,
    name: "Example Engineering Ltd",
    year: 2024,
    occupation: "Engineer",
    enrichment: {
      sector: "Engineering",
      companySize: null,
      source: null,
      researchedAt: null,
    },
  },
];

function Search() {
  const [search, setSearch] = useState("");
  const [year, setYear] = useState("");
  const [sector, setSector] = useState("");
  const [occupation, setOccupation] = useState("");
  const [companySize, setCompanySize] = useState("");

  const filteredCompanies = useMemo(() => {
    return mockCompanies.filter((company) => {
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
        company.enrichment?.companySize === companySize;

      return (
        matchesSearch &&
        matchesYear &&
        matchesSector &&
        matchesOccupation &&
        matchesCompanySize
      );
    });
  }, [search, year, sector, occupation, companySize]);

  function handleSearch() {
    console.log("Search filters:", {
      search,
      year,
      sector,
      occupation,
      companySize,
    });
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