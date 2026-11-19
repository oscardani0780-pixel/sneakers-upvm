import base64
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw

# 1. Ruta de tu logo original y carpeta de plantillas
logo_path = Path("static/img/logo_upvm.png")
templates_dir = Path("templates")

# 2. Generar versión circular en base64 para el favicon de la pestaña
img = Image.open(logo_path).convert("RGBA")
size = min(img.size)
left = (img.width - size) // 2
top = (img.height - size) // 2
img = img.crop((left, top, left + size, top + size)).resize((128, 128), Image.Resampling.LANCZOS)

mask = Image.new("L", (128, 128), 0)
draw = ImageDraw.Draw(mask)
draw.ellipse((0, 0, 128, 128), fill=255)

circular = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
circular.paste(img, (0, 0), mask)

buffer = BytesIO()
circular.save(buffer, format="PNG")
favicon_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

favicon_tag = f'<link rel="icon" type="image/png" href="data:image/png;base64,{favicon_b64}">'
logo_img_tag = '<img src="{{ url_for(\'static\', filename=\'img/logo_upvm.png\') }}" alt="Logo Sneakers UPVM" class="logo-nav-img">'

# 3. Actualizar todos los .html dentro de templates/
for html_file in templates_dir.glob("*.html"):
    content = html_file.read_text(encoding="utf-8")
    original = content

    if 'rel="icon"' not in content and "</head>" in content:
        content = content.replace("</head>", f"    {favicon_tag}\n</head>", 1)

    if "logo-nav-img" not in content and "Sneakers <span>UPVM</span>" in content:
        content = content.replace(
            "Sneakers <span>UPVM</span>",
            f"{logo_img_tag}\n                <span>Sneakers <span>UPVM</span></span>",
            1,
        )

    if content != original:
        html_file.write_text(content, encoding="utf-8")
        print(f"Actualizado: {html_file.name}")

print("Proceso terminado.")