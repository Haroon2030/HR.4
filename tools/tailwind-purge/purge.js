// Regenerates backend/static/css/tailwind.min.css from tailwind.full.css,
// keeping only the classes used in templates / JS / Python.
//
//   cd tools/tailwind-purge && npm i purgecss@6 && node purge.js
//
// Run it again whenever a template starts using a Tailwind class that is
// missing from the purged file. After running, bump the ?v= on the
// tailwind.min.css <link> in backend/templates/base.html.
const { PurgeCSS } = require('purgecss');
const fs = require('fs');
const path = require('path');

const backend = path.resolve(__dirname, '../../backend') + '/';
const colors = 'slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|primary';

(async () => {
  const result = await new PurgeCSS().purge({
    content: [
      backend + 'templates/**/*.html',
      backend + 'apps/**/*.html',
      backend + 'apps/**/*.py',
      backend + 'config/**/*.py',
      backend + 'static/js/hr-*.js',
      backend + 'static/css/hr-*.css',
      backend + 'static/css/login.css',
      backend + 'static/css/maintenance-report.css',
    ],
    css: [path.join(__dirname, 'tailwind.full.css')],
    defaultExtractor: (c) => c.match(/[^\s"'`<>=(){}\\,;|]+/g) || [],
    // dashboard.html builds these names dynamically: bg-{{ color }}-100, hover:bg-{{ color }}-700 ...
    safelist: { greedy: [new RegExp('^(hover:)?(bg|text|border)-(' + colors + ')-(50|100|200|500|600|700|800)$')] },
    keyframes: false,
    fontFace: false,
    variables: false,
  });
  const out = backend + 'static/css/tailwind.min.css';
  fs.writeFileSync(out, result[0].css);
  console.log(out, fs.statSync(out).size, 'bytes');
})();
