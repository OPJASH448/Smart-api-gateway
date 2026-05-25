from fastapi import FastAPI

app = FastAPI()

fake_products = {
    1: {"id": 1, "name": "Laptop", "price": 50000},
    2: {"id": 2, "name": "Phone", "price": 30000},
}

@app.get("/products/{product_id}")
async def get_product(product_id: int):
    return fake_products.get(product_id)
