"""Category weights of the 100-point model (fixed by the assignment)."""

AI_PROJECT_DEPTH_MAX = 40
PYTHON_BACKEND_MAX = 30
CLOUD_FULLSTACK_MAX = 15
GITHUB_MAX = 10
ENGINEERING_DEPTH_MAX = 5

TOTAL_MAX = (
    AI_PROJECT_DEPTH_MAX
    + PYTHON_BACKEND_MAX
    + CLOUD_FULLSTACK_MAX
    + GITHUB_MAX
    + ENGINEERING_DEPTH_MAX
)
assert TOTAL_MAX == 100

# Shallow-AI-project penalty bounds (assignment: 5-15 points).
PENALTY_MIN = 5
PENALTY_MAX = 15
