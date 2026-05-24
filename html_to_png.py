import weasyprint
import subprocess
import os

files = [
    ('package-upgrade.html', 'package-upgrade'),
    ('package-basic.html',   'package-basic'),
    ('package-compare.html', 'package-compare'),
]

base = os.path.dirname(os.path.abspath(__file__))

# 390px wide (iPhone logical), tall enough for any content
# 3x pixel ratio → 1170px wide PNG (physical)
page_css = weasyprint.CSS(string='''
    @page {
        size: 390px 5000px;
        margin: 0;
    }
    body { margin: 0 !important; padding: 0 !important; }
''')

for html_file, name in files:
    html_path = os.path.join(base, html_file)
    pdf_path  = os.path.join(base, f'{name}.pdf')
    png_path  = os.path.join(base, f'{name}.png')

    weasyprint.HTML('file://' + html_path).write_pdf(pdf_path, stylesheets=[page_css])
    print(f'PDF: {name}.pdf')

    # 288dpi = 3x of 96dpi (standard screen resolution)
    # -trim removes blank bottom area, +repage resets canvas
    subprocess.run([
        'convert', '-density', '288', '-quality', '95',
        '-trim', '+repage',
        f'{pdf_path}[0]',
        png_path
    ], check=True)
    print(f'PNG: {name}.png')

    dims = subprocess.check_output(['identify', '-format', '%wx%h', png_path]).decode()
    print(f'  Size: {dims}')
