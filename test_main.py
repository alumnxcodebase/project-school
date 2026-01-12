from fastapi import FastAPI

app = FastAPI(
    title="Test API",
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.get("/")
async def root():
    return {"message": "Test API working"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("test_main:app", host="0.0.0.0", port=8001, reload=True)