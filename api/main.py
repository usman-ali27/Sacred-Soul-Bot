from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


from endpoints import router as api_router
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/api/status")
def get_status():
    return {"status": "ICT_BOT API running"}

# TODO: Add endpoints for MT5 connect, bot control, config, etc.
