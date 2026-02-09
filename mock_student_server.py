from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class TwoSumRequest(BaseModel):
    nums: list[int]
    target: int

class TwoSumResponse(BaseModel):
    indices: list[int]

@app.post("/two-sum")
def two_sum(request: TwoSumRequest) -> TwoSumResponse:
    # Correct Implementation
    lookup = {}
    for i, num in enumerate(request.nums):
        diff = request.target - num
        if diff in lookup:
            return TwoSumResponse(indices=[lookup[diff], i])
        lookup[num] = i
    return TwoSumResponse(indices=[])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)
