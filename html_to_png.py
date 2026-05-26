import weasyprint
import subprocess
import os
from PIL import Image
import numpy as np

files = [
    ('package-upgrade.html', 'package-upgrade'),
    ('package-basic.html',   'package-basic'),
    ('package-compare.html', 'package-compare'),
]

base = os.path.dirname(os.path.abspath(__file__))

# 390px wide, tall enough for all content — no trim needed
page_css = weasyprint.CSS(string='''
    @page { size: 390px 5000px; margin: 0; }
    body  { margin: 0 !important; padding: 0 !important; }
    .page { width: 390px !important; }
''')

for html_file, name in files:
    html_path = os.path.join(base, html_file)
    pdf_path  = os.path.join(base, f'{name}.pdf')
    png_path  = os.path.join(base, f'{name}.png')
    tmp_path  = os.path.join(base, f'{name}_tmp.png')

    weasyprint.HTML('file://' + html_path).write_pdf(pdf_path, stylesheets=[page_css])

    # 288 dpi = 3× (96 dpi baseline) → 1170 px wide
    subprocess.run([
        'convert', '-density', '288', '-quality', '95',
        f'{pdf_path}[0]', tmp_path
    ], check=True)

    # Crop ONLY from the bottom — don't touch the top
    img = Image.open(tmp_path).convert('RGB')
    arr = np.array(img)
    # Bottom-left pixel is the PDF blank background (white)
    bg = arr[-1, 0].tolist()
    # Find last row that differs from background
    mask = np.any(arr != bg, axis=2)
    rows = np.where(np.any(mask, axis=1))[0]
    last_row = int(rows[-1]) + 4  # small buffer
    img = img.crop((0, 0, img.width, last_row))
    img.save(png_path, quality=95)
    os.remove(tmp_path)

    print(f'Done: {name}.png  {img.width}×{img.height}')
