"""Generate a simple black & white circular camera icon as camera.ico.

Design: white circular badge with a thin black ring, holding a black
camera body (rounded rect + top viewfinder bump) and a white lens.
Transparent background so it sits cleanly on any surface.
"""
from PIL import Image, ImageDraw

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

cx, cy = SIZE // 2, SIZE // 2
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)

# Outer white badge circle
badge_r = SIZE * 0.46
d.ellipse(
    [cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r],
    fill=WHITE,
)

# Thin black ring around the badge
ring = 6
d.ellipse(
    [cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r],
    outline=BLACK,
    width=ring,
)

# --- Camera body (black rounded rectangle) ---
body_w = SIZE * 0.56
body_h = SIZE * 0.34
body_left = cx - body_w / 2
body_top = cy - body_h / 2 + SIZE * 0.04
body_right = cx + body_w / 2
body_bottom = body_top + body_h
radius = int(body_h * 0.28)
d.rounded_rectangle(
    [body_left, body_top, body_right, body_bottom],
    radius=radius,
    fill=BLACK,
)

# --- Top viewfinder bump (small black rounded rect centered on top) ---
bump_w = body_w * 0.30
bump_h = body_h * 0.42
bump_left = cx - bump_w / 2
bump_top = body_top - bump_h * 0.9
bump_right = cx + bump_w / 2
bump_bottom = body_top + bump_h * 0.1
d.rounded_rectangle(
    [bump_left, bump_top, bump_right, bump_bottom],
    radius=int(bump_h * 0.4),
    fill=BLACK,
)

# --- Lens (white circle + thin black inner ring) ---
lens_r = body_h * 0.32
lcx, lcy = cx, cy + SIZE * 0.02
d.ellipse(
    [lcx - lens_r, lcy - lens_r, lcx + lens_r, lcy + lens_r],
    fill=WHITE,
)
d.ellipse(
    [lcx - lens_r, lcy - lens_r, lcx + lens_r, lcy + lens_r],
    outline=BLACK,
    width=max(2, int(lens_r * 0.18)),
)
# tiny center dot for the lens pupil
inner = lens_r * 0.42
d.ellipse(
    [lcx - inner, lcy - inner, lcx + inner, lcy + inner],
    fill=BLACK,
)

# --- Save multi-resolution ICO ---
out = "camera.ico"
sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
img.save(out, sizes=sizes)
print("saved", out, "with sizes", sizes)
