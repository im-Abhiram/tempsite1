/**
 * Thamarayyath Employee Portal — Global Client Scripts
 * Handles mobile sidebar toggle, alert dismissal, client validations, and UI interactions.
 */

document.addEventListener('DOMContentLoaded', function () {
  // ── 1. Mobile Sidebar Toggle ──────────────────────────────────────────
  const sidebar = document.getElementById('portalSidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');

  if (sidebar && sidebarToggle) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('show');
    });

    // Close when clicking outside on small screens
    document.addEventListener('click', function (e) {
      if (window.innerWidth < 992) {
        if (sidebar.classList.contains('show') && !sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
          sidebar.classList.remove('show');
        }
      }
    });
  }

  // ── 2. Auto Dismiss Flash Alerts ───────────────────────────────────────
  const flashMessages = document.getElementById('flashMessages');
  if (flashMessages) {
    setTimeout(function () {
      const alerts = flashMessages.querySelectorAll('.alert:not(.alert-danger)');
      alerts.forEach(function (alert) {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) {
          bsAlert.close();
        }
      });
    }, 6000);
  }

  // ── 3. Tooltip & Popover Initialization ────────────────────────────────
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // ── 4. Form Double-Submit Protection ───────────────────────────────────
  const forms = document.querySelectorAll('form[data-prevent-double-submit="true"], .needs-double-submit-guard');
  forms.forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.checkValidity && !form.checkValidity()) {
        return; // Let browser HTML5 validation fire
      }
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...';
        // Re-enable after 8s in case network interrupted
        setTimeout(function () {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
        }, 8000);
      }
    });
  });

  // ── 5. Quick Filter for Tables ─────────────────────────────────────────
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

  // ── 6. Confirm Modal / Buttons ─────────────────────────────────────────
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
