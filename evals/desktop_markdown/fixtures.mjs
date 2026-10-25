const prose = 'The worker reads each item, checks its status, and writes the result.\n\n'
const markdown = 'Read **the result** and [the guide](https://example.com/guide). Use `worker.run()`.\n\n'
const code = `${markdown}\n\`\`\`python\nprice = "$5"\nprint(price)\n\`\`\`\n\n`
const math = 'Use $x^2 + y^2$ and \\(z + 1\\).\n\n[/math]\nx = 2\n[/math]\n\n'
const currency = 'Rent costs $500 and utilities $150. R$ 12.345 is another price.\n\n'
const unicode = '日本語の説明です。結果を確認して続行します。 Ελληνικό κείμενο. Résumé.\n\n'

function sized(text, length) {
  return text.repeat(Math.ceil(length / text.length)).slice(0, length)
}

export const cases = [
  { name: 'short-prose', text: sized(prose, 1024), iterations: 200 },
  { name: 'prose-16k', text: sized(prose, 16384), iterations: 100 },
  { name: 'prose-64k', text: sized(prose, 65536), iterations: 40 },
  { name: 'prose-512k', text: sized(prose, 524288), iterations: 40 },
  { name: 'markdown-16k', text: sized(markdown, 16384), iterations: 100 },
  { name: 'code-16k', text: code.repeat(100), iterations: 100 },
  { name: 'unicode-16k', text: sized(unicode, 16384), iterations: 100 },
  { name: 'math-control', text: math.repeat(200), iterations: 60 },
  { name: 'currency-control', text: currency.repeat(200), iterations: 60 },
  { name: 'cjk-dollar-control', text: '$変数（説明）$ then $x + 1$ and R$ 12.345.\n\n'.repeat(300), iterations: 600 },
  {
    name: 'escaped-dollar-control',
    text: 'Literal \\$5, \\*emphasis\\*, and \\(x + 1\\).\n\n'.repeat(300),
    iterations: 60
  },
  {
    name: 'backslash-control',
    text: 'Windows path C:\\Users\\Example with ordinary prose.\n\n'.repeat(300),
    iterations: 60
  }
]
