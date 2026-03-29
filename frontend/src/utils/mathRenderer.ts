import katex from 'katex';

/**
 * Renders LaTeX math expressions found in HTML content.
 * Supports $$...$$ for display math and $...$ for inline math.
 */
export const renderMathInHTML = (html: string): string => {
  if (!html || (!html.includes('$'))) return html;

  // First handle display math: $$...$$
  html = html.replace(/\$\$([\s\S]*?)\$\$/g, (_match, latex: string) => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: true,
        throwOnError: false,
        output: 'html',
      });
    } catch {
      return `<span style="color:red;">${latex}</span>`;
    }
  });

  // Then handle inline math: $...$
  // Negative lookbehind for $ to avoid matching already-processed $$
  html = html.replace(/(?<!\$)\$(?!\$)((?:[^$\\]|\\.)+?)\$(?!\$)/g, (_match, latex: string) => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: false,
        throwOnError: false,
        output: 'html',
      });
    } catch {
      return `<span style="color:red;">${latex}</span>`;
    }
  });

  return html;
};
