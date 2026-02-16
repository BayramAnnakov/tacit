const sharp = require('sharp');

async function createBg() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
    <rect width="100%" height="100%" fill="#0D1117"/>
    <rect y="0" width="100%" height="5" fill="#00D4AA"/>
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile('bg.png');
  console.log('bg.png created');
}

createBg().catch(console.error);
