// Function to find Python code snippets
function captureCodeSnippet() {
  const codeBlocks = document.querySelectorAll('pre, code');
  let lastCodeBlock = codeBlocks[codeBlocks.length - 1];
  if (lastCodeBlock) {
    let codeText = lastCodeBlock.textContent || lastCodeBlock.innerText;
    // Ensure the snippet contains Python-related code (e.g., imports or function definitions)
    if (codeText.includes('import') || codeText.includes('def ') || codeText.includes('class ')) {
      chrome.runtime.sendMessage({ action: 'sendCode', code: codeText });
    }
  }
}

// Call the function when the content script is executed
captureCodeSnippet();