# coding: utf-8

"""Gomoku (five-in-a-row) game — single-file implementation."""

import tkinter as tk
from tkinter import messagebox

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BOARD_SIZE = 15
CELL_SIZE = 36
MARGIN = 30
BOARD_PX = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)
PIECE_RADIUS = 15

# Colors
BOARD_BG = "#DEB887"
LINE_COLOR = "#000000"
BLACK_COLOR = "#000000"
WHITE_COLOR = "#FFFFFF"
WHITE_OUTLINE = "#000000"


# ---------------------------------------------------------------------------
# GomokuGame class
# ---------------------------------------------------------------------------
class GomokuGame:
    """Gomoku (five-in-a-row) game on a 15x15 board."""

    def __init__(self, master):
        """Create canvas, init board state, bind click event."""
        self.master = master
        self.master.title("Gomoku - Black's turn")
        self.canvas = tk.Canvas(master, width=BOARD_PX, height=BOARD_PX, bg=BOARD_BG)
        self.canvas.pack()

        # Use list comprehension to avoid reference-copy from [[None]*15]*15
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = 1  # 1 = black (first), 2 = white

        self.draw_board()
        self.canvas.bind("<Button-1>", self.on_click)

    # ------------------------------------------------------------------
    def draw_board(self):
        """Draw the board background and grid lines."""
        for i in range(BOARD_SIZE):
            # Horizontal line
            y = MARGIN + i * CELL_SIZE
            self.canvas.create_line(
                MARGIN,
                y,
                MARGIN + CELL_SIZE * (BOARD_SIZE - 1),
                y,
                fill=LINE_COLOR,
            )
            # Vertical line
            x = MARGIN + i * CELL_SIZE
            self.canvas.create_line(
                x,
                MARGIN,
                x,
                MARGIN + CELL_SIZE * (BOARD_SIZE - 1),
                fill=LINE_COLOR,
            )

    # ------------------------------------------------------------------
    def on_click(self, event):
        """Map pixel coordinate to nearest grid intersection, validate bounds."""
        col = round((event.x - MARGIN) / CELL_SIZE)
        row = round((event.y - MARGIN) / CELL_SIZE)

        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            if self.board[row][col] is None:
                self.place_piece(row, col)

    # ------------------------------------------------------------------
    def place_piece(self, row, col):
        """Draw a piece at (row, col), update board, check winner."""
        # Pixel coordinates of the intersection
        x = MARGIN + col * CELL_SIZE
        y = MARGIN + row * CELL_SIZE
        r = PIECE_RADIUS

        if self.current_player == 1:
            color = BLACK_COLOR
            outline_color = BLACK_COLOR
        else:
            color = WHITE_COLOR
            outline_color = WHITE_OUTLINE

        self.canvas.create_oval(
            x - r,
            y - r,
            x + r,
            y + r,
            fill=color,
            outline=outline_color,
        )

        # Update board state
        self.board[row][col] = self.current_player

        # Check win condition
        if self.check_winner(row, col):
            name = "Black" if self.current_player == 1 else "White"
            messagebox.showinfo("Game Over", f"{name} wins!")
            self.reset()
        else:
            # Switch player
            self.current_player = 2 if self.current_player == 1 else 1
            turn = "Black" if self.current_player == 1 else "White"
            self.master.title(f"Gomoku - {turn}'s turn")

    # ------------------------------------------------------------------
    def check_winner(self, row, col):
        """Check if the last move at (row, col) results in a win.

        Scans 4 directions (horizontal, vertical, two diagonals).
        For each direction, counts consecutive same-color pieces bidirectionally.
        """
        player = self.board[row][col]
        if player is None:
            return False

        # Four direction vectors: (dx, dy)
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]

        for dx, dy in directions:
            count = 1  # count the piece itself

            # Scan in the positive direction
            r, c = row + dx, col + dy
            while (
                0 <= r < BOARD_SIZE
                and 0 <= c < BOARD_SIZE
                and self.board[r][c] == player
            ):
                count += 1
                r += dx
                c += dy

            # Scan in the negative direction
            r, c = row - dx, col - dy
            while (
                0 <= r < BOARD_SIZE
                and 0 <= c < BOARD_SIZE
                and self.board[r][c] == player
            ):
                count += 1
                r -= dx
                c -= dy

            if count >= 5:
                return True

        return False

    # ------------------------------------------------------------------
    def reset(self):
        """Clear the canvas and reset board state for a new game."""
        self.canvas.delete("all")
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = 1
        self.master.title("Gomoku - Black's turn")
        self.draw_board()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Gomoku")
    root.resizable(False, False)
    game = GomokuGame(root)
    root.mainloop()
