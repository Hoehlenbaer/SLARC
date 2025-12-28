# Pathfinder Logic v3.5:
# Costmap-based A* with height, clearance, terrain-aware slope cost,
# live search animation, RGBA overlay, and height-map path overlay.

import matplotlib
matplotlib.use("TkAgg")  # or "QtAgg"

import matplotlib.pyplot as plt
import numpy as np
import heapq
import random
import math
from scipy.ndimage import distance_transform_edt, gaussian_filter

# --- CONFIGURATION ---
GRID_SIZE = 100
BLOCK_SIZE = 8
NUM_BLOCKS = 25

# Costmap weights
W_OCC = 255
W_CLEARANCE = 160
W_SLOPE = 200     # much stronger slope weight
W_BASE = 1

MIN_CLEARANCE = 2

# Clamp slope angle for cost (radians)
MAX_SLOPE_ANGLE = np.deg2rad(30)  # ~30°

# RGBA colors
C_EXPLORED = np.array([0.0, 0.4, 1.0, 0.6])
C_FRONTIER = np.array([0.0, 1.0, 1.0, 0.6])
C_PATH = np.array([1.0, 1.0, 0.0, 1.0])
C_START = np.array([0.0, 1.0, 0.0, 1.0])
C_TARGET = np.array([1.0, 0.0, 0.0, 1.0])


# ---------------------------------------------------------
# HEIGHT MAP GENERATION
# ---------------------------------------------------------
def generate_height_map(size):
    h = np.random.rand(size, size)
    h = gaussian_filter(h, sigma=5)  # less smoothing -> more variation
    return h * 8.0  # height range ~0..8 m


# ---------------------------------------------------------
# CLEARANCE MAP
# ---------------------------------------------------------
def compute_clearance_map(grid):
    wall_mask = (grid == 1)
    return distance_transform_edt(~wall_mask)


# ---------------------------------------------------------
# COSTMAP GENERATION
# ---------------------------------------------------------
def compute_costmap(grid, height, clearance):
    costmap = np.zeros_like(grid, dtype=float)

    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE):

            if grid[x, y] == 1:
                costmap[x, y] = W_OCC
                continue

            c = W_BASE

            # Clearance penalty
            if clearance[x, y] < MIN_CLEARANCE:
                c += W_CLEARANCE * (MIN_CLEARANCE - clearance[x, y])

            # Slope penalty (using slope angle, nonlinear)
            local_slope_cost = 0.0
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                    dh = abs(height[nx, ny] - height[x, y])      # rise in meters
                    slope_angle = math.atan2(dh, 1.0)            # radians, run=1m
                    slope_angle = min(slope_angle, MAX_SLOPE_ANGLE)
                    # Quadratic penalty -> steep slopes get very expensive
                    local_slope_cost += (slope_angle ** 2)

            c += W_SLOPE * local_slope_cost
            costmap[x, y] = c

    # Percentile normalization for visualization
    p95 = np.percentile(costmap, 95)
    if p95 <= 0:
        p95 = 1.0
    costmap_vis = np.clip(costmap / p95, 0, 1) * 255

    # Walls pure white
    costmap_vis[grid == 1] = 255

    return costmap, costmap_vis


# ---------------------------------------------------------
# A* WITH RGBA OVERLAY VISUALIZATION
# ---------------------------------------------------------
def heuristic(a, b):
    # Euclidean distance (still fine; slope handled in cost)
    return math.dist(a, b)


def get_neighbors(node):
    dirs = [
        (0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),
        (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)
    ]
    for dx, dy, cost in dirs:
        yield dx, dy, cost


def a_star_costmap(costmap, start, target, fig, overlay_img, overlay):
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {start: 0}

    iteration = 0

    while open_set:
        _, current = heapq.heappop(open_set)

        if current == target:
            return came_from

        x, y = current

        # Mark explored
        overlay[x, y] = C_EXPLORED

        if iteration % 20 == 0:
            overlay_img.set_data(overlay)
            fig.canvas.draw()
            fig.canvas.flush_events()

        iteration += 1

        for dx, dy, step_cost in get_neighbors(current):
            nx, ny = x + dx, y + dy

            if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                continue

            if costmap[nx, ny] >= 255:  # treated as blocked
                continue

            new_cost = g_score[current] + step_cost + costmap[nx, ny]

            if new_cost < g_score.get((nx, ny), float('inf')):
                g_score[(nx, ny)] = new_cost
                priority = new_cost + heuristic((nx, ny), target)
                heapq.heappush(open_set, (priority, (nx, ny)))
                came_from[(nx, ny)] = current

                # Mark frontier
                overlay[nx, ny] = C_FRONTIER

    return None


# ---------------------------------------------------------
# MAP GENERATION
# ---------------------------------------------------------
def generate_map():
    grid = np.zeros((GRID_SIZE, GRID_SIZE))

    grid[0, :] = grid[-1, :] = grid[:, 0] = grid[:, -1] = 1

    def random_free():
        return random.randint(2, GRID_SIZE - 3), random.randint(2, GRID_SIZE - 3)

    while True:
        start = random_free()
        target = random_free()
        if abs(start[0] - target[0]) + abs(start[1] - target[1]) > GRID_SIZE // 3:
            break

    safe = {(r, c) for r in range(start[0] - 2, start[0] + 3)
                    for c in range(start[1] - 2, start[1] + 3)}
    safe |= {(r, c) for r in range(target[0] - 2, target[0] + 3)
                     for c in range(target[1] - 2, target[1] + 3)}

    blocks = 0
    while blocks < NUM_BLOCKS:
        r = random.randint(1, GRID_SIZE - BLOCK_SIZE - 1)
        c = random.randint(1, GRID_SIZE - BLOCK_SIZE - 1)

        block = {(r + i, c + j) for i in range(BLOCK_SIZE) for j in range(BLOCK_SIZE)}
        if block & safe:
            continue

        for br, bc in block:
            grid[br, bc] = 1

        blocks += 1

    return grid, start, target


# ---------------------------------------------------------
# MAIN VISUALIZATION
# ---------------------------------------------------------
def run():
    grid, start, target = generate_map()
    height = generate_height_map(GRID_SIZE)

    # Obstacles as tall columns in the height map
    height[grid == 1] = 10.0

    # Visualization-only saturation for height
    natural_max = height[grid == 0].max()      # highest real hill
    vis_max = natural_max * 1.10               # 10% margin
    height_vis = np.clip(height, 0, vis_max)   # for plotting only

    clearance = compute_clearance_map(grid)
    costmap, costmap_vis = compute_costmap(grid, height, clearance)

    # Height map figure (using height_vis)
    plt.figure(figsize=(6, 6))
    plt.imshow(height_vis, cmap="terrain", origin="upper")
    plt.colorbar()
    plt.title("Height Map (Obstacles Included, Saturated)")

    plt.ion()
    fig, ax = plt.subplots(figsize=(9, 9))

    # Background grayscale costmap
    ax.imshow(costmap_vis, cmap="gray", origin="upper")

    # RGBA overlay
    overlay = np.zeros((GRID_SIZE, GRID_SIZE, 4), dtype=float)
    overlay[start] = C_START
    overlay[target] = C_TARGET
    overlay_img = ax.imshow(overlay, origin="upper")

    ax.set_title("Costmap + Live A* Search (Height + Clearance + Slope)")

    came_from = a_star_costmap(costmap, start, target, fig, overlay_img, overlay)

    # Draw final path on overlay
    if came_from:
        curr = target
        while curr != start:
            x, y = curr
            overlay[x, y] = C_PATH
            curr = came_from[curr]
        overlay_img.set_data(overlay)
        fig.canvas.draw()
        fig.canvas.flush_events()
        print("Path found")
    else:
        print("No path found")

    # Draw final path on height map (using height_vis for consistency)
    if came_from:
        fig2, ax2 = plt.subplots(figsize=(6, 6))
        ax2.imshow(height_vis, cmap="terrain", origin="upper")
        ax2.set_title("Height Map with Final Path")

        curr = target
        path_points = []
        while curr != start:
            path_points.append(curr)
            curr = came_from[curr]
        path_points.append(start)

        px = [p[1] for p in path_points]
        py = [p[0] for p in path_points]

        ax2.plot(px, py, color="yellow", linewidth=2)
        ax2.scatter([start[1]], [start[0]], c="green", s=50)
        ax2.scatter([target[1]], [target[0]], c="red", s=50)

        plt.show()

    plt.ioff()
    plt.show()


if __name__ == "__main__":
    run()
