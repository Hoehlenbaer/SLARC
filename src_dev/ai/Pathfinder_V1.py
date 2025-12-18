import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
import heapq
import random
import math

# --- CONFIGURATION ---
GRID_SIZE = 100           # Increased size to accommodate larger blocks
BLOCK_SIZE = 8           # The "realistic" obstacle size (4x4)
NUM_BLOCKS = 50          # How many 4x4 blocks to place
# ---------------------

# State values
EMPTY, WALL, START, END, EXPLORED, PATH = 0, 1, 2, 3, 4, 5
COLORS = ['#FFFFFF', '#2C3E50', '#27AE60', '#E74C3C', '#7FB3D5', '#F1C40F']
CMAP = ListedColormap(COLORS)

def heuristic(current, target, start):
    dx, dy = abs(current[0] - target[0]), abs(current[1] - target[1])
    h = math.sqrt(dx**2 + dy**2)
    # Tie-breaker nudge to keep the path straight
    dx1, dy1 = current[0] - target[0], current[1] - target[1]
    dx2, dy2 = start[0] - target[0], start[1] - target[1]
    return h + abs(dx1*dy2 - dx2*dy1) * 0.001

def get_neighbors(node, grid, size):
    neighbors = []
    # 8-way movement: (dx, dy, cost)
    directions = [
        (0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),
        (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)
    ]
    for dx, dy, cost in directions:
        nx, ny = node[0] + dx, node[1] + dy
        if 0 <= nx < size and 0 <= ny < size and grid[nx][ny] != WALL:
            neighbors.append(((nx, ny), cost))
    return neighbors

def generate_map():
    grid = np.zeros((GRID_SIZE, GRID_SIZE))
    # Border walls
    grid[0, :] = grid[-1, :] = grid[:, 0] = grid[:, -1] = WALL
    
    start, target = (GRID_SIZE - 3, 2), (2, GRID_SIZE - 3)
    
    # Safe zones to ensure start/end are not buried in a 4x4 block
    safe = {(r, c) for r in range(start[0]-2, start[0]+3) for c in range(start[1]-2, start[1]+3)} | \
           {(r, c) for r in range(target[0]-2, target[0]+3) for c in range(target[1]-2, target[1]+3)}

    # Place 4x4 blocks
    blocks_placed = 0
    while blocks_placed < NUM_BLOCKS:
        r, c = random.randint(1, GRID_SIZE - BLOCK_SIZE - 1), random.randint(1, GRID_SIZE - BLOCK_SIZE - 1)
        
        # Create a candidate 4x4 block
        block_cells = {(r+i, c+j) for i in range(BLOCK_SIZE) for j in range(BLOCK_SIZE)}
        
        # Check if block overlaps safe zones
        if not (block_cells & safe):
            for br, bc in block_cells:
                grid[br, bc] = WALL
            blocks_placed += 1

    grid[start], grid[target] = START, END
    return grid, start, target

def a_star_visual():
    grid, start, target = generate_map()

    plt.ion()
    fig, ax = plt.subplots(figsize=(9, 9))
    img = ax.imshow(grid, cmap=CMAP, vmin=0, vmax=5, origin='upper')
    ax.set_title("A* with 4x4 Block Obstacles")

    open_set = []
    heapq.heappush(open_set, (0, 0, start))
    came_from, g_score, count = {}, {start: 0}, 0
    
    found = False
    step_counter = 0

    while open_set:
        current = heapq.heappop(open_set)[2]
        if current == target:
            found = True
            break

        if current != start:
            grid[current] = EXPLORED

        for neighbor, step_cost in get_neighbors(current, grid, GRID_SIZE):
            tentative_g = g_score[current] + step_cost
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + heuristic(neighbor, target, start)
                count += 1
                heapq.heappush(open_set, (f_score, count, neighbor))

        # Update visualization every few steps to prevent UI lag/freezing
        step_counter += 1
        if step_counter % 5 == 0:
            img.set_data(grid)
            plt.pause(0.001)
            fig.canvas.flush_events() # Force the window to process updates

    if found:
        # Paint final path
        curr = target
        while curr in came_from:
            if curr != target: grid[curr] = PATH
            curr = came_from[curr]
            img.set_data(grid)
            plt.pause(0.01)
        print("Shortest path found!")
    else:
        print("No path found.")

    plt.ioff()
    plt.show()

if __name__ == "__main__":
    a_star_visual()