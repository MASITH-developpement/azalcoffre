// Guardian Auto-Generated Functions


// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}

function saveQuickCreate(...args) { console.log('saveQuickCreate', args); }

function updateBulkSelection(...args) { console.log('updateBulkSelection', args); }

function handleRowClick(event, id, url) {
    if (event.target.type === 'checkbox' || event.target.tagName === 'BUTTON' || event.target.closest('button')) {
        return;
    }
    window.location.href = url;
}

function openPrintPreview(...args) { console.log('openPrintPreview', args); }