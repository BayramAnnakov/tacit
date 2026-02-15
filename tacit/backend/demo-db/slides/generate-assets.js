const sharp = require('sharp');

async function createGradient(filename, color1, color2, angle = '135') {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="563">
    <defs>
      <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${color1}"/>
        <stop offset="100%" style="stop-color:${color2}"/>
      </linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#g)"/>
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(filename);
}

async function createAccentBar(filename, color, w, h) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
    <rect width="100%" height="100%" fill="${color}" rx="4"/>
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(filename);
}

async function main() {
  // Dark backgrounds
  await createGradient('bg-dark.png', '#0D1117', '#161B22');
  await createGradient('bg-dark-accent.png', '#0D1117', '#1A2332');
  // Cyan accent bar
  await createAccentBar('accent-bar.png', '#00D4AA', 600, 4);
  await createAccentBar('accent-dot.png', '#00D4AA', 12, 12);
  console.log('Assets generated');
}

main().catch(console.error);
