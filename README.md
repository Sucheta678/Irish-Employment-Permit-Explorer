# Irish Employment Permit Explorer

A full-stack web app for exploring which employers in Ireland are issued employment permits.

Ireland's Department of Enterprise, Trade and Employment (DETE) publishes yearly lists of the employers that were issued employment permits, with the number each one received. The lists contain only employer names and permit counts. This project cleans them, adds each employer's business sector and an estimated company size, and makes the data easy to search and compare.

The project is under active development.

## Features

The app is designed to let you:

- search for an employer by name;
- filter employers by year, sector and company size;
- see a company's permit totals and how they change over the years;
- compare two employers side by side;
- export results as CSV.

## How it works

```
DETE permit files → cleaning + enrichment (Python) → MySQL → FastAPI → React UI
```

- **Data:** the DETE company-level permit files are cleaned and normalised. Each employer is matched against the Companies Registration Office (CRO) register to find its NACE industry sector, and keyword rules and web lookups fill the gaps. Company size is an estimate.
- **Backend:** a FastAPI service serves the data as a JSON API.
- **Frontend:** a React + TypeScript app for searching, viewing and comparing employers.

## Tech stack

- **Frontend:** React, TypeScript, Vite, React Router
- **Backend:** Python, FastAPI, Pydantic
- **Database:** MySQL
- **Data processing:** Python, pandas

## Project structure

```
frontend/          React + TypeScript app
backend/           FastAPI service
database/          scripts that load the cleaned data into MySQL
data/raw/          DETE permit files, CRO register and the enriched dataset
data-description/  exploratory data analysis notebook
```

## Data sources

- Company-level employment permit statistics published by DETE.
- The CRO company register, used to look up each employer's sector.
