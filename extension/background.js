chrome.runtime.onInstalled.addListener(() => {
  console.log('AI Code Capture Extension Installed');
});

// Function to send the captured code to the Flask server
function sendCodeToServer(code) {
  fetch('http://localhost:5000/submit_code', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code: code })
  })
  .then(response => response.json())
  .then(data => {
    console.log('Code received and processed:', data);
    alert('Code processed successfully! Syntax OK: ' + data.syntax_ok);
  })
  .catch(error => {
    console.error('Error sending code to server:', error);
  });
}