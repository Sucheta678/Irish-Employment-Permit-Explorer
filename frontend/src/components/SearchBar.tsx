interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSearch: () => void;
}

function SearchBar({ value, onChange, onSearch }: SearchBarProps) {
  return (
    <div className="search-bar">
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search companies..."
        aria-label="Search companies"
      />

      <button type="button" onClick={onSearch}>
        Search
      </button>
    </div>
  );
}

export default SearchBar;