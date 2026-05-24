import weasyprint
import subprocess
import os

files = [
    ('package-upgrade.html', 'package-upgrade'),
    ('package-basic.html',   'package-basic'),
    ('package-compare.html', 'package-compare'),
]

base = os.path.dirname(os.path.abspath(__file__))

# CSS to force single tall page (no pagination)
page_css = weasyprint.CSS(string='''
    @page {
        size: 760px 6000px;
        margin: 0;
    }
    body {
        margin: 0 !important;
        padding: 0 !important;
    }
''')

for html_file, name in files:
    html_path = os.path.join(base, html_file)
    pdf_path  = os.path.join(base, f'{name}.pdf')
    png_path  = os.path.join(base, f'{name}.png')
    url = 'file://' + html_path

    # HTML -> PDF (single tall page, no page breaks)
    weasyprint.HTML(url).write_pdf(pdf_path, stylesheets=[page_css])
    print(f'PDF done: {name}.pdf')

    # PDF -> PNG at 300dpi, flatten to remove alpha, trim whitespace
    subprocess.run([
        'convert', '-density', '300', '-quality', '95',
        '-trim', '+repage',
        pdf_path + '[0]',  # only first page (all content on one page)
        png_path
    ], check=True)
    print(f'PNG done: {name}.png')
