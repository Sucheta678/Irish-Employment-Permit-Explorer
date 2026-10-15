import { Link } from "react-router-dom";

function Header() {
  return (
    <header>
      <nav>
        <Link to="/">Irish Employment Permit Explorer</Link>

        <div>
          <Link to="/search">Search</Link>
          <Link to="/compare">Compare</Link>
        </div>
      </nav>
    </header>
  );
}

export default Header;