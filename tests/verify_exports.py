"""Check generated PDF/PPTX page count, order, dimensions and rendering."""
import re,zipfile,json
from pathlib import Path
from pypdf import PdfReader
import pypdfium2 as pdfium
from PIL import Image,ImageOps,ImageDraw
from io import BytesIO

root=Path('reports')
titles=['Overview','Sales trends','Product intelligence','Customer intelligence','Geography','Commercial','Supply chain','Pharma risk','Tax & terms']
reader=PdfReader(root/'verified-export.pdf')
assert len(reader.pages)==9
for page,title in zip(reader.pages,titles):
    assert title in page.extract_text(),title
    assert float(page.mediabox.width)>float(page.mediabox.height)
pdf=pdfium.PdfDocument(root/'verified-export.pdf')
contact=Image.new('RGB',(1440,900),'#e5e8ec')
for i,page in enumerate(pdf):
    im=page.render(scale=.4).to_pil().convert('RGB');im.thumbnail((480,300));contact.paste(im,((i%3)*480,(i//3)*300));page.close()
contact.save(root/'export-contact-sheet.png')
pdf.close()
with zipfile.ZipFile(root/'verified-export.pptx') as z:
    slides=sorted(n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))
    assert len(slides)==9
    xml=z.read('ppt/presentation.xml').decode()
    assert '12192000' in xml and '6858000' in xml
    media=[n for n in z.namelist() if n.startswith('ppt/media/') and n.endswith('.png')]
    assert len(media)==9
    dimensions=[]
    for name in media:
        image=Image.open(BytesIO(z.read(name)));dimensions.append(image.size);assert image.width>=3000
(root/'export-verification.json').write_text(json.dumps({'pdf_pages':9,'pptx_slides':9,'order':titles,'slide_images':dimensions,'result':'passed'},indent=2))
print('Passed: 9 ordered landscape PDF pages, 9 widescreen PPTX slides, high-resolution images.')
