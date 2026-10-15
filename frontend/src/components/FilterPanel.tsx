interface FilterPanelProps {
  year: string;
  sector: string;
  occupation: string;
  companySize: string;
  onYearChange: (value: string) => void;
  onSectorChange: (value: string) => void;
  onOccupationChange: (value: string) => void;
  onCompanySizeChange: (value: string) => void;
}

function FilterPanel({
  year,
  sector,
  occupation,
  companySize,
  onYearChange,
  onSectorChange,
  onOccupationChange,
  onCompanySizeChange,
}: FilterPanelProps) {
  return (
    <aside className="filter-panel">
      <h2>Filters</h2>

      <label>
        Year
        <select value={year} onChange={(event) => onYearChange(event.target.value)}>
          <option value="">All years</option>
          <option value="2026">2026</option>
          <option value="2025">2025</option>
          <option value="2024">2024</option>
        </select>
      </label>

      <label>
        Sector
        <select value={sector} onChange={(event) => onSectorChange(event.target.value)}>
          <option value="">All sectors</option>
          <option value="Technology">Technology</option>
          <option value="Healthcare">Healthcare</option>
          <option value="Finance">Finance</option>
        </select>
      </label>

      <label>
        Occupation
        <select
          value={occupation}
          onChange={(event) => onOccupationChange(event.target.value)}
        >
          <option value="">All occupations</option>
          <option value="Software Developer">Software Developer</option>
          <option value="Data Analyst">Data Analyst</option>
          <option value="Engineer">Engineer</option>
        </select>
      </label>

      <label>
        Company size
        <select
          value={companySize}
          onChange={(event) => onCompanySizeChange(event.target.value)}
        >
          <option value="">All sizes</option>
          <option value="Small">Small</option>
          <option value="Medium">Medium</option>
          <option value="Large">Large</option>
          <option value="Unknown">Unknown</option>
        </select>
      </label>
    </aside>
  );
}

export default FilterPanel;