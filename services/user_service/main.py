from fastapi import FastAPI

app = FastAPI(title="User Service")

@app.get("/users")
async def get_users():
    return {
        "status": "success",
        "data": [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"}
        ],
        "service": "user-service"
    }

@app.get("/health")
@app.get("/users/health")
async def health():
    return {"status": "ok", "service": "user-service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
