"""Run the moving-object detector and render its top track on real SPHEREx frames."""

import struct
import zlib
from pathlib import Path

import numpy as np

from detector import find_candidates


def write_png(path, rgb):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    height, width = rgb.shape[:2]
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = b"".join(b"\0" + row.tobytes() for row in rgb)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def render_frames(images, track):
    levels = np.clip((np.nan_to_num(images) - 0.045) / (2.1 - 0.045), 0, 1)
    grayscale = np.rint(12 + 240 * np.arcsinh(6 * levels) / np.arcsinh(6)).astype(np.uint8)
    enlarged = grayscale.repeat(2, axis=1).repeat(2, axis=2)
    frames = np.repeat(enlarged[..., None], 3, axis=3)
    height, width = frames.shape[1:3]
    yy, xx = np.ogrid[:height, :width]
    for epoch, (x, y) in zip(track.epochs, track.positions_xy):
        distance = np.hypot(xx - (2 * x + 0.5), yy - (2 * y + 0.5))
        frames[epoch][(distance >= 16) & (distance <= 20)] = (12, 20, 25)
        frames[epoch][(distance >= 17) & (distance <= 19)] = (78, 222, 201)

    gap = 8
    figure = np.full((2 * height + gap, 2 * width + gap, 3), 37, dtype=np.uint8)
    for epoch, frame in enumerate(frames):
        row, col = divmod(epoch, 2)
        top, left = row * (height + gap), col * (width + gap)
        figure[top:top + height, left:left + width] = frame
    return figure


def main():
    folder = Path(__file__).resolve().parent
    with np.load(folder / "spherex_3i_atlas.npz") as data:
        images, times = data["images"], data["times"]
        dates = data["dates"]
        expected = data["expected_xy"]

    tracks = find_candidates(images, times, max_speed=60, min_support=0.8)
    if not tracks:
        raise SystemExit("The detector found no tracks in the four SPHEREx exposures.")
    top = tracks[0]
    output = folder / "spherex-result.png"
    write_png(output, render_frames(images, top))

    positions = np.array(top.positions_xy)
    offsets = np.linalg.norm(positions - expected[list(top.epochs)], axis=1)
    print(f"SPHEREx | 3I/ATLAS | {dates[0][:10]} UTC")
    print(f"Baseline ranking: 1 of {len(tracks)} candidates | {len(top.epochs)}/{len(images)} frames linked")
    print("UTC         Detected (x, y)    Offset from ephemeris")
    for epoch, (x, y), offset in zip(top.epochs, top.positions_xy, offsets):
        print(f"{dates[epoch][11:19]}    ({x:3d}, {y:3d})           {offset:.2f} px")
    print(f"Maximum offset: {offsets.max():.2f} px")
    print(f"Figure: {output.name}  (read left to right, top to bottom)")


if __name__ == "__main__":
    main()
