import type { FilterOptions } from "../types";

// The API returns sizes in no particular order.
const SIZE_ORDER = ["Micro", "Small", "Medium", "Large"];

interface FilterPanelProps {
  options: FilterOptions;
  sector: string;
  companySize: string;
  onSectorChange: (value: string) => void;
  onCompanySizeChange: (value: string) => void;
}

function FilterPanel({
  options,
  sector,
  companySize,
  onSectorChange,
  onCompanySizeChange,
}: FilterPanelProps) {
  const sizes = [...options.sizes].sort(
    (a, b) => SIZE_ORDER.indexOf(a) - SIZE_ORDER.indexOf(b),
  );

  return (
    <aside className="filter-panel">
      <h2>Filters</h2>

      <label>
        Sector
        <select value={sector} onChange={(event) => onSectorChange(event.target.value)}>
          <option value="">All sectors</option>
          {options.sectors.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>

      <label>
        Company size
        <select
          value={companySize}
          onChange={(event) => onCompanySizeChange(event.target.value)}
        >
          <option value="">All sizes</option>
          {sizes.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
    </aside>
  );
}

export default FilterPanel;
