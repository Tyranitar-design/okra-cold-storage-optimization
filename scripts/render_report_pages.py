from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path


def font(size: int) -> ImageFont.ImageFont:
    for candidate in [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def make_contact_sheet(pages: list[Path], out_path: Path) -> None:
    thumbs: list[Image.Image] = []
    label_font = font(18)
    for page_path in pages:
        img = Image.open(page_path).convert("RGB")
        img.thumbnail((260, 360))
        canvas = Image.new("RGB", (280, 400), "white")
        x = (280 - img.width) // 2
        canvas.paste(img, (x, 28))
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 6), page_path.stem, fill="#222222", font=label_font)
        thumbs.append(canvas)

    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 280, rows * 400), "white")
    for idx, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((idx % cols) * 280, (idx // cols) * 400))
    sheet.save(out_path, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    images = convert_from_path(str(args.pdf), dpi=args.dpi)
    page_paths: list[Path] = []
    for idx, image in enumerate(images, start=1):
        out = args.out_dir / f"page-{idx:02d}.png"
        image.save(out)
        page_paths.append(out)
    make_contact_sheet(page_paths, args.out_dir / "contact_sheet.png")
    print(f"rendered pages: {len(page_paths)}")
    print(f"output: {args.out_dir}")


if __name__ == "__main__":
    main()
