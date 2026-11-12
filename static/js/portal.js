/**
 * Thamarayyath Employee Portal — Premium Dark SaaS Client Scripts
 * Handles sidebar collapse/toggle, live digital clock, Chart.js dark-mode styling,
 * global search keyboard shortcut, alert auto-dismiss, and form submit guards.
 */

document.addEventListener('DOMContentLoaded', function () {
  // ── 1. Desktop Sidebar Collapse & Mobile Drawer ───────────────────────
  const layout = document.querySelector('.portal-layout');
  const sidebar = document.getElementById('portalSidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');

  // Restore saved collapse state on desktop
  if (layout && window.innerWidth >= 1024) {
    if (localStorage.getItem('portal_sidebar_collapsed') === 'true') {
      layout.classList.add('sidebar-collapsed');
    }
  }

  // Desktop collapse toggle
  if (sidebarCollapseBtn && layout) {
    sidebarCollapseBtn.addEventListener('click', function (e) {
      e.preventDefault();
      layout.classList.toggle('sidebar-collapsed');
      const isCollapsed = layout.classList.contains('sidebar-collapsed');
      localStorage.setItem('portal_sidebar_collapsed', isCollapsed ? 'true' : 'false');
    });
  }

  // Mobile drawer toggle
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function (e) {
      e.stopPropagation();
      sidebar.classList.toggle('show');
    });

    // Close mobile drawer when clicking outside
    document.addEventListener('click', function (e) {
      if (window.innerWidth < 1024) {
        if (sidebar.classList.contains('show') && !sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
          sidebar.classList.remove('show');
        }
      }
    });
  }

  // ── 2. Live Topbar Digital Clock ──────────────────────────────────────
  const clockEl = document.getElementById('topbarLiveClock');
  if (clockEl) {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    function updateClock() {
      const now = new Date();
      const dayName = days[now.getDay()];
      const day = String(now.getDate()).padStart(2, '0');
      const monthName = months[now.getMonth()];
      let hours = now.getHours();
      const minutes = String(now.getMinutes()).padStart(2, '0');
      const seconds = String(now.getSeconds()).padStart(2, '0');
      const ampm = hours >= 12 ? 'PM' : 'AM';
      hours = hours % 12;
      hours = hours ? hours : 12;
      const formattedHours = String(hours).padStart(2, '0');
      clockEl.innerHTML = `${dayName}, ${day} ${monthName} &bull; ${formattedHours}:${minutes}:${seconds} ${ampm}`;
    }
    updateClock();
    setInterval(updateClock, 1000);
  }

  // ── 3. Keyboard Shortcut for Global Search (Ctrl+K or /) ───────────────
  const searchInput = document.getElementById('globalSearchInput');
  if (searchInput) {
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey && e.key.toLowerCase() === 'k') || (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA')) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    });
  }

  // ── 4. Global Chart.js Dark Theme Configuration ───────────────────────
  if (window.Chart) {
    Chart.defaults.color = '#9BAAB5';
    Chart.defaults.font.family = "'Inter', system-ui, -apple-system, sans-serif";
    Chart.defaults.font.size = 11.5;
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.06)';
    
    // Default plugins configuration
    if (Chart.defaults.plugins && Chart.defaults.plugins.tooltip) {
      Chart.defaults.plugins.tooltip.backgroundColor = '#192630';
      Chart.defaults.plugins.tooltip.titleColor = '#F2F5F7';
      Chart.defaults.plugins.tooltip.bodyColor = '#9BAAB5';
      Chart.defaults.plugins.tooltip.borderColor = '#2C3C47';
      Chart.defaults.plugins.tooltip.borderWidth = 1;
      Chart.defaults.plugins.tooltip.padding = 10;
      Chart.defaults.plugins.tooltip.cornerRadius = 8;
    }
  }

  // ── 5. Auto-Dismiss Flash Alerts ──────────────────────────────────────
  const flashMessages = document.getElementById('flashMessages');
  if (flashMessages) {
    setTimeout(function () {
      const alerts = flashMessages.querySelectorAll('.alert:not(.alert-danger)');
      alerts.forEach(function (alert) {
        if (window.bootstrap && bootstrap.Alert) {
          const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
          if (bsAlert) bsAlert.close();
        }
      });
    }, 6000);
  }

  // ── 6. Tooltips Initialization ────────────────────────────────────────
  if (window.bootstrap && bootstrap.Tooltip) {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
    });
  }

  // ── 7. Form Double-Submit Protection ──────────────────────────────────
  const forms = document.querySelectorAll('form[data-prevent-double-submit="true"], .needs-double-submit-guard');
  forms.forEach(function (form) {
    form.addEventListener('submit', function () {
      if (form.checkValidity && !form.checkValidity()) {
        return; // HTML5 validation halted submit
      }
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...';
        setTimeout(function () {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
        }, 8000);
      }
    });
  });

  // ── 8. Table Client-Side Quick Search ─────────────────────────────────
  const tableQuickFilters = document.querySelectorAll('[data-table-filter]');
  tableQuickFilters.forEach(function (input) {
    const tableId = input.getAttribute('data-table-filter');
    const table = document.getElementById(tableId);
    if (!table) return;

    input.addEventListener('keyup', function () {
      const query = input.value.toLowerCase().trim();
      const rows = table.querySelectorAll('tbody tr');
      rows.forEach(function (row) {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
      });
    });
  });

  // ── 9. Confirmation Action Guard ──────────────────────────────────────
  const confirmButtons = document.querySelectorAll('[data-confirm]');
  confirmButtons.forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      const message = btn.getAttribute('data-confirm') || 'Are you sure you want to proceed with this action?';
      if (!window.confirm(message)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  });
});
