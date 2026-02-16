const pptxgen = require('pptxgenjs');
const path = require('path');
const html2pptx = require('/Users/bayramannakov/.claude/plugins/cache/anthropic-agent-skills/document-skills/00756142ab04/skills/pptx/scripts/html2pptx');

async function build() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = 'Bayram Annakov';
  pptx.title = 'Tacit - Extract Team Knowledge from PR Reviews';

  // Slide 1: Title with illustration background
  // First create a blank slide with the illustration, then layer HTML text on top
  const slide1 = pptx.addSlide();
  // Add illustration as full-bleed background
  slide1.addImage({
    path: path.join(__dirname, 'illustration-title.png'),
    x: 0, y: 0, w: '100%', h: '100%',
  });
  // Dark gradient overlay (left-to-right) for text readability
  slide1.addShape(pptx.shapes.RECTANGLE, {
    x: 0, y: 0, w: '55%', h: '100%',
    fill: { color: '0D1117', transparency: 5 },
  });
  slide1.addShape(pptx.shapes.RECTANGLE, {
    x: '55%', y: 0, w: '15%', h: '100%',
    fill: { color: '0D1117', transparency: 50 },
  });
  // Teal top bar
  slide1.addShape(pptx.shapes.RECTANGLE, {
    x: 0, y: 0, w: '100%', h: 0.06,
    fill: { color: '00D4AA' },
  });
  // Title text
  slide1.addText('TACIT', {
    x: 0.7, y: 1.5, w: 5, h: 1.2,
    fontSize: 64, fontFace: 'Arial', color: '00D4AA',
    bold: true, charSpacing: 8,
  });
  slide1.addText('Extract team knowledge\nfrom PR reviews', {
    x: 0.7, y: 2.7, w: 5, h: 1,
    fontSize: 20, fontFace: 'Arial', color: 'C9D1D9',
  });
  slide1.addText('Built with Claude Agent SDK and Opus 4.6', {
    x: 0.7, y: 3.9, w: 5, h: 0.4,
    fontSize: 13, fontFace: 'Arial', color: '8B949E',
  });

  // Slides 2-6: standard HTML conversion
  const htmlSlides = ['slide2.html', 'slide3.html', 'slide4.html', 'slide5.html', 'slide6.html'];
  for (const file of htmlSlides) {
    console.log(`Processing ${file}...`);
    await html2pptx(path.join(__dirname, file), pptx);
  }

  const outPath = path.join(__dirname, '..', 'tacit-demo.pptx');
  await pptx.writeFile({ fileName: outPath });
  console.log(`Presentation saved to ${outPath}`);
}

build().catch(e => { console.error(e); process.exit(1); });
