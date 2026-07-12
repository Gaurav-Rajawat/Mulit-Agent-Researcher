from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pipeline import run_research_pipeline

app = FastAPI(title="Tough Research API")


class ResearchRequest(BaseModel):
    topic: str


@app.get("/")
def home():
    return {"message": "Tough Research API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/research")
def research(request: ResearchRequest):
    try:
        result = run_research_pipeline(request.topic)

        return {
            "status": "success",
            "topic": request.topic,
            "data": result
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Research pipeline failed: {str(e)}"
        )