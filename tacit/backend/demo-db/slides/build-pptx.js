const pptxgen = require('pptxgenjs');
const html2pptx = require('/Users/bayramannakov/.claude/plugins/cache/anthropic-agent-skills/document-skills/00756142ab04/skills/pptx/scripts/html2pptx');
const path = require('path');

async function build() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = 'Bayram Annakov';
  pptx.title = 'Tacit: Continuous Team Knowledge Extraction';

  const slides = [
    'slide1-title.html',
    'slide2-problem.html',
    'slide3-solution.html',
    'slide4-demo.html',
    'slide5-provenance.html',
    'slide6-results.html',
    'slide7-closing.html',
  ];

  for (const file of slides) {
    const htmlPath = path.join(__dirname, file);
    console.log(`Processing ${file}...`);
    await html2pptx(htmlPath, pptx);
  }

  const outputPath = path.join(__dirname, '..', 'tacit-demo.pptx');
  await pptx.writeFile({ fileName: outputPath });
  console.log(`Presentation saved to ${outputPath}`);
}

build().catch(err => {
  console.error('Build failed:', err.message);
  process.exit(1);
});
