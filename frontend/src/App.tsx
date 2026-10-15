import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./App.css";

import Header from "./components/Header";

import Home from "./pages/Home";
import Search from "./pages/Search";
import CompanyProfile from "./pages/CompanyProfile";
import Compare from "./pages/Compare";

function App() {
  return (
    <BrowserRouter>
      <Header />

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<Search />} />
          <Route path="/company/:id" element={<CompanyProfile />} />
          <Route path="/compare" element={<Compare />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;