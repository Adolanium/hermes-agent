import { describe, expect, it } from 'vitest'

import { normalizeFilePreviewMath } from './markdown-preprocess'

describe('file preview prose without math', () => {
  it('preserves Unicode, Markdown structure, and line endings', () => {
    const prose = '# Résumé 日本語\r\n\r\n- **Ready**\r\n- [Guide](https://example.com)\r\n\r\nUse `worker.run()`.\r\n'

    expect(normalizeFilePreviewMath(prose)).toBe(
      '# Résumé 日本語\r\n\r\n- **Ready**\r\n- [Guide](https://example.com)\r\n\r\nUse `worker.run()`.\r\n'
    )
  })

  it('still normalizes alternative delimiters and currency between ordinary paragraphs', () => {
    const text = 'Before.\n\n\\(x + 1\\) and [/inline]y[/inline].\n\n[/math]\nz = 2\n[/math]\n\nRent $500.\n\nAfter.'
    const expected = 'Before.\n\n$x + 1$ and $y$.\n\n$$\nz = 2\n$$\n\nRent \\$500.\n\nAfter.'

    expect(normalizeFilePreviewMath(text)).toBe(expected)
  })
})
