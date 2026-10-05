import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

const HEX = '(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\\w-])'
// A hex literal inside a longer style string ("1px solid #fff", "color:#fff", "bg-[#fff]"), or a whole string that is
// the value of a colour-like property or attribute. A bare '#add' used as an anchor or id is not a colour.
const HEX_EMBEDDED = `(?:[:(,\\[]\\s*|\\b(?:solid|dashed|dotted|double|inset|none|\\d+px|\\d+r?em|\\d+%)\\s+)#${HEX}`
const HEX_WHOLE = `^\\s*#${HEX}\\s*$`
const COLOUR_KEYS = 'color|colour|background|bg|fill|stroke|border|shadow|outline|accent|caret|stop|tint|gradient'
const NAMED_COLOURS = [
  'red', 'blue', 'green', 'black', 'white', 'gray', 'grey', 'orange', 'purple', 'yellow', 'pink', 'brown', 'cyan', 'magenta',
  'teal', 'navy', 'maroon', 'olive', 'lime', 'aqua', 'fuchsia', 'silver', 'gold', 'indigo', 'violet', 'crimson', 'coral',
  'salmon', 'tan', 'beige', 'ivory', 'khaki', 'lavender', 'turquoise', 'tomato', 'plum', 'orchid', 'azure',
].join('|')
const FUNC = 'rgb|rgba|hsl|hsla|hwb|oklch|oklab|lab|lch'
const HEX_MSG = 'No hex colour literals. Use a design token (var(--...)) from tokens/tokens.json.'
const FUNC_MSG = 'No rgb, hsl or oklch colour literals. Use a design token (var(--...)) from tokens/tokens.json.'
const NAMED_MSG = 'No named CSS colours. Use a design token (var(--...)) from tokens/tokens.json.'
export const COLOUR_GUARD = [
  { selector: `Literal[value=/${HEX_EMBEDDED}/]`, message: HEX_MSG },
  { selector: `TemplateElement[value.raw=/${HEX_EMBEDDED}/]`, message: HEX_MSG },
  { selector: `Property[key.name=/${COLOUR_KEYS}/i] > Literal[value=/${HEX_WHOLE}/]`, message: HEX_MSG },
  { selector: `Property[key.value=/${COLOUR_KEYS}/i] > Literal[value=/${HEX_WHOLE}/]`, message: HEX_MSG },
  { selector: `JSXAttribute[name.name=/${COLOUR_KEYS}/i] > Literal[value=/${HEX_WHOLE}/]`, message: HEX_MSG },
  { selector: `JSXAttribute[name.name=/${COLOUR_KEYS}/i] > JSXExpressionContainer > Literal[value=/${HEX_WHOLE}/]`, message: HEX_MSG },
  { selector: `Literal[value=/\\b(${FUNC})\\(/i]`, message: FUNC_MSG },
  { selector: `TemplateElement[value.raw=/\\b(${FUNC})\\(/i]`, message: FUNC_MSG },
  { selector: `Literal[value=/^\\s*(${NAMED_COLOURS})\\s*$/i]`, message: NAMED_MSG },
]

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'e2e/.state', 'playwright-report', 'test-results', 'src/api/schema.d.ts'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2022, globals: { ...globals.browser, ...globals.node } },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
      // Colour literals live only in tokens/tokens.json (generated into src/styles/tokens.css). Components use tokens.
      'no-restricted-syntax': ['error', ...COLOUR_GUARD],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
)
