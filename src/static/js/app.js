/**
 * TVMaze-Sync Web UI JavaScript utilities
 */

// Toast notification system
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toast-container');
    },

    show(message, type = 'info', duration = 3000) {
        if (!this.container) this.init();

        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };

        const toast = document.createElement('div');
        toast.className = `toast-enter ${colors[type] || colors.info} text-white px-4 py-3 rounded-lg shadow-lg flex items-center space-x-2 min-w-[250px]`;
        toast.innerHTML = `
            <span class="flex-1">${message}</span>
            <button onclick="this.parentElement.remove()" class="text-white/80 hover:text-white">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        `;

        this.container.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => {
                toast.classList.remove('toast-enter');
                toast.classList.add('toast-exit');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
    },

    success(message, duration) { this.show(message, 'success', duration); },
    error(message, duration) { this.show(message, 'error', duration); },
    warning(message, duration) { this.show(message, 'warning', duration); },
    info(message, duration) { this.show(message, 'info', duration); }
};

// Initialize Toast on load
document.addEventListener('DOMContentLoaded', () => Toast.init());

// HTMX event handlers
document.body.addEventListener('htmx:afterRequest', function(evt) {
    // Handle trigger endpoint responses
    if (evt.detail.pathInfo.requestPath === '/trigger') {
        const response = evt.detail.xhr.response;
        try {
            const data = JSON.parse(response);
            if (data.status === 'triggered') {
                Toast.success('Sync triggered successfully!');
            } else if (data.status === 'already_running') {
                Toast.warning('Sync already in progress');
            } else if (data.error) {
                Toast.error(data.error);
            }
        } catch (e) {
            // Non-JSON response
        }
    }
});

document.body.addEventListener('htmx:responseError', function(evt) {
    const status = evt.detail.xhr.status;
    if (status === 401) {
        Toast.error('Session expired. Please log in again.');
        setTimeout(() => window.location.href = '/login', 1500);
    } else if (status >= 500) {
        Toast.error('Server error. Please try again.');
    }
});

// Utility functions
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

function formatDate(dateStr) {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString();
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        Toast.success('Copied to clipboard!');
    }).catch(() => {
        Toast.error('Failed to copy');
    });
}

// Debounce utility for search inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
