import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from pipeline import run_research_pipeline

load_dotenv()
print("FASTAPI_API_KEY =", os.getenv("FASTAPI_API_KEY"))

app = FastAPI(title="RougeAI API")

# Add CORS Middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("FASTAPI_API_KEY", "supersecretapikey")


def is_valid_api_key(request: Request) -> bool:
    key = request.headers.get(API_KEY_NAME)
    if key == API_KEY:
        return True

    query_key = request.query_params.get("api_key")
    if query_key == API_KEY:
        return True

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        if token == API_KEY:
            return True

    return False


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Ignore OPTIONS requests so CORS preflight can succeed
        if request.url.path == "/research" and request.method != "OPTIONS":
            if not is_valid_api_key(request):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Could not validate credentials"},
                )
        return await call_next(request)


# app.add_middleware(ApiKeyMiddleware)


class ResearchRequest(BaseModel):
    topic: str


@app.get("/")
def home():
    return {"message": "RougeAI API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}

### ORGINAL FASTAPI
# @app.post("/research")
# def research(request: ResearchRequest):
#     try:
#         result = run_research_pipeline(request.topic)

#         return {
#             "status": "success",
#             "topic": request.topic,
#             "data": result,
#         }

#     except Exception as e:
#         print(e)
#         raise HTTPException(
#             status_code=500,
#             detail=f"Research pipeline failed",
#         )



## TEMP FASTAPI 
import traceback

@app.post("/research")
def research(request: ResearchRequest):
    try:
        result = run_research_pipeline(request.topic)

        return {
            "status": "success",
            "topic": request.topic,
            "data": result,
        }

    except Exception as e:
        traceback.print_exc()   # prints full error in terminal

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
