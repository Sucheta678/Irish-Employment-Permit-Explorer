from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.companies import router as companies_router


app = FastAPI(
    title="Irish Employment Permit Explorer API",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(companies_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}