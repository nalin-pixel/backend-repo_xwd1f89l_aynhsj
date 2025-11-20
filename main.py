import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Tuple
import random

from database import create_document, get_documents
from schemas import SudokuStat

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class NewGameRequest(BaseModel):
    difficulty: str = "easy"  # easy, medium, hard

class SubmitStatRequest(BaseModel):
    player_id: str
    difficulty: str
    seconds: int
    solved: bool
    mistakes: int = 0

# Sudoku generation/solving utilities
GRID_SIZE = 9
SUBGRID = 3

Board = List[List[int]]


def is_safe(board: Board, row: int, col: int, num: int) -> bool:
    # Row and column
    for i in range(9):
        if board[row][i] == num or board[i][col] == num:
            return False
    # Subgrid
    start_row = row - row % 3
    start_col = col - col % 3
    for r in range(start_row, start_row + 3):
        for c in range(start_col, start_col + 3):
            if board[r][c] == num:
                return False
    return True


def find_empty(board: Board) -> Optional[Tuple[int, int]]:
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                return (r, c)
    return None


def solve_board(board: Board) -> bool:
    empty = find_empty(board)
    if not empty:
        return True
    r, c = empty
    nums = list(range(1, 10))
    random.shuffle(nums)
    for n in nums:
        if is_safe(board, r, c, n):
            board[r][c] = n
            if solve_board(board):
                return True
            board[r][c] = 0
    return False


def generate_full_board() -> Board:
    board = [[0 for _ in range(9)] for _ in range(9)]
    # Fill diagonal subgrids to speed solving
    for k in range(0, 9, 3):
        nums = list(range(1, 10))
        random.shuffle(nums)
        idx = 0
        for r in range(k, k + 3):
            for c in range(k, k + 3):
                board[r][c] = nums[idx]
                idx += 1
    solve_board(board)
    return board


def remove_cells(board: Board, difficulty: str) -> Board:
    puzzle = [row[:] for row in board]
    # Set number of clues based on difficulty
    if difficulty == "easy":
        removals = 35
    elif difficulty == "medium":
        removals = 45
    else:
        removals = 55
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)
    removed = 0
    for r, c in cells:
        if removed >= removals:
            break
        backup = puzzle[r][c]
        puzzle[r][c] = 0
        # Ensure still solvable (not strictly enforcing uniqueness for simplicity)
        test = [row[:] for row in puzzle]
        if not solve_board(test):
            puzzle[r][c] = backup
        else:
            removed += 1
    return puzzle


def generate_puzzle(difficulty: str) -> Tuple[Board, Board]:
    full = generate_full_board()
    puzzle = remove_cells(full, difficulty)
    return puzzle, full


@app.get("/")
def read_root():
    return {"message": "Sudoco backend running"}


@app.post("/api/new-game")
def new_game(payload: NewGameRequest):
    diff = payload.difficulty.lower()
    if diff not in ["easy", "medium", "hard"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty")
    puzzle, solution = generate_puzzle(diff)
    return {"puzzle": puzzle, "solution": solution}


@app.post("/api/statistics")
def submit_statistics(payload: SubmitStatRequest):
    # Persist game statistics
    doc_id = create_document("sudokustat", payload.model_dump())
    return {"id": doc_id, "status": "ok"}


@app.get("/api/statistics")
def get_statistics(limit: int = 50, difficulty: Optional[str] = None):
    filt = {}
    if difficulty:
        filt["difficulty"] = difficulty
    docs = get_documents("sudokustat", filt, min(limit, 200))
    # Convert ObjectId and datetime for JSON serialization
    def serialize(d):
        d["_id"] = str(d.get("_id"))
        if "created_at" in d:
            d["created_at"] = d["created_at"].isoformat()
        if "updated_at" in d:
            d["updated_at"] = d["updated_at"].isoformat()
        return d
    return {"items": [serialize(d) for d in docs]}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
