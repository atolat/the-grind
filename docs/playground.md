# Code Playground

Run Python and Go snippets directly in the browser. No setup needed.

---

## Python

<div id="py-playground">
<div style="display: flex; gap: 8px; margin-bottom: 8px;">
    <button onclick="runPython()" id="py-run-btn" style="background: #238636; color: #fff; border: 1px solid #2ea043; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;">&#9654; Run</button>
    <button onclick="clearOutput()" style="background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;">Clear</button>
    <span id="py-status" style="color: #8b949e; font-size: 0.8rem; line-height: 32px; margin-left: 8px;">Loading Python runtime...</span>
</div>
<textarea id="py-editor" spellcheck="false" style="width: 100%; height: 300px; background: #0d1117; color: #c9d1d9; border: 1px solid #21262d; border-radius: 6px; padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; tab-size: 4; resize: vertical; line-height: 1.5;">
# Python 3.12+ (Pyodide)
# Try it out!

from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: 'Point') -> float:
        return ((self.x - other.x)**2 + (self.y - other.y)**2) ** 0.5

a = Point(0, 0)
b = Point(3, 4)
print(f"Distance: {a.distance_to(b)}")

# Try match/case
status = 200
match status:
    case 200:
        print("OK")
    case 404:
        print("Not Found")
    case _:
        print(f"Status: {status}")
</textarea>
<pre id="py-output" style="background: #161b22; color: #7ee787; border: 1px solid #21262d; border-radius: 6px; padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; min-height: 60px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; margin-top: 0;"></pre>
</div>

<script src="https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js"></script>
<script>
let pyodide = null;

async function initPyodide() {
    try {
        pyodide = await loadPyodide();
        document.getElementById('py-status').textContent = 'Ready';
        document.getElementById('py-status').style.color = '#7ee787';
        document.getElementById('py-run-btn').disabled = false;
    } catch (e) {
        document.getElementById('py-status').textContent = 'Failed to load runtime';
        document.getElementById('py-status').style.color = '#f85149';
    }
}

async function runPython() {
    if (!pyodide) {
        document.getElementById('py-output').textContent = 'Python runtime still loading...';
        return;
    }
    const code = document.getElementById('py-editor').value;
    const outputEl = document.getElementById('py-output');
    const statusEl = document.getElementById('py-status');

    statusEl.textContent = 'Running...';
    statusEl.style.color = '#d29922';
    outputEl.textContent = '';

    try {
        // Redirect stdout/stderr
        pyodide.runPython(`
import sys, io
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
`);
        await pyodide.runPythonAsync(code);
        const stdout = pyodide.runPython('sys.stdout.getvalue()');
        const stderr = pyodide.runPython('sys.stderr.getvalue()');
        outputEl.textContent = stdout + stderr;
        if (!outputEl.textContent) outputEl.textContent = '(no output)';
        statusEl.textContent = 'Done';
        statusEl.style.color = '#7ee787';
    } catch (e) {
        outputEl.textContent = e.message;
        outputEl.style.color = '#f85149';
        statusEl.textContent = 'Error';
        statusEl.style.color = '#f85149';
        setTimeout(() => { outputEl.style.color = '#7ee787'; }, 0);
    }
}

function clearOutput() {
    document.getElementById('py-output').textContent = '';
}

// Handle Tab key in editor
document.addEventListener('DOMContentLoaded', function() {
    const editor = document.getElementById('py-editor');
    if (editor) {
        editor.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = this.selectionStart;
                const end = this.selectionEnd;
                this.value = this.value.substring(0, start) + '    ' + this.value.substring(end);
                this.selectionStart = this.selectionEnd = start + 4;
            }
            // Ctrl/Cmd + Enter to run
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                runPython();
            }
        });
    }
});

initPyodide();
</script>

<small style="color: #8b949e;">**Tip:** Press `Ctrl+Enter` (or `Cmd+Enter`) to run. Tab key inserts spaces.</small>

<small style="color: #8b949e;">**Note:** `threading` and file I/O are not available in the browser runtime. Use this for logic, data structures, and language features.</small>

---

## Go

Powered by [goplay.tools](https://goplay.tools/) -- a better Go Playground with syntax highlighting and autocomplete. Runs on real Go servers.

<iframe src="https://goplay.tools/" style="width: 100%; height: 500px; border: 1px solid #21262d; border-radius: 6px;" loading="lazy"></iframe>

<small style="color: #8b949e;">If the embed doesn't load, <a href="https://goplay.tools/" target="_blank">open goplay.tools directly</a>. Some browser privacy settings may block third-party iframes.</small>
