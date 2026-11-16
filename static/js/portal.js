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
  const sidebarBackdrop = document.getElementById('sidebarBackdrop');

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

  // Mobile drawer controls with backdrop & body scroll lock
  function closeMobileDrawer() {
    if (sidebar) sidebar.classList.remove('show');
    if (sidebarBackdrop) sidebarBackdrop.classList.remove('show');
    document.body.classList.remove('sidebar-open');
  }

  function openMobileDrawer() {
    if (sidebar) sidebar.classList.add('show');
    if (sidebarBackdrop) sidebarBackdrop.classList.add('show');
    document.body.classList.add('sidebar-open');
  }

  function toggleMobileDrawer() {
    if (!sidebar) return;
    if (sidebar.classList.contains('show')) {
      closeMobileDrawer();
    } else {
      openMobileDrawer();
    }
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleMobileDrawer();
    });
  }

  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener('click', function (e) {
      e.preventDefault();
      closeMobileDrawer();
    });
  }

  // Close mobile drawer when clicking outside or tapping any nav link
  if (sidebar) {
    sidebar.querySelectorAll('.nav-link').forEach(function (link) {
      link.addEventListener('click', function () {
        if (window.innerWidth < 1024) {
          closeMobileDrawer();
        }
      });
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sidebar && sidebar.classList.contains('show')) {
      closeMobileDrawer();
    }
  });

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
    if (tableId === 'dailyAttendanceTable') return; // Handled coordinately in Section 11
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
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-confirm]');
    if (btn && btn.tagName !== 'FORM') {
      const message = btn.getAttribute('data-confirm') || 'Are you sure you want to proceed with this action?';
      if (!window.confirm(message)) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  });

  document.addEventListener('submit', function (e) {
    const form = e.target.closest('form[data-confirm]');
    if (form) {
      const message = form.getAttribute('data-confirm') || 'Are you sure you want to proceed?';
      if (!window.confirm(message)) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  });

  // ── 10. Unobtrusive Action Handlers (Print, History-Back, Auto-Submit) ─
  document.addEventListener('click', function (e) {
    const printBtn = e.target.closest('[data-action="print"]');
    if (printBtn) {
      e.preventDefault();
      window.print();
    }
    const backBtn = e.target.closest('[data-action="history-back"]');
    if (backBtn) {
      e.preventDefault();
      history.back();
    }
  });

  document.addEventListener('change', function (e) {
    const autoSubmit = e.target.closest('[data-auto-submit="true"]');
    if (autoSubmit && autoSubmit.form) {
      autoSubmit.form.submit();
    }
  });

  // ── 11. Daily Attendance Tracker Filter (Pending/Unmarked, Present, Absent, etc.) ─
  const dailyTable = document.getElementById('dailyAttendanceTable');
  const statusFilterTriggers = document.querySelectorAll('[data-status-filter]');
  const statCards = document.querySelectorAll('.stat-card[data-status-filter]');
  const filterCountEl = document.getElementById('visibleRowCount');
  const noMatchRow = document.getElementById('noFilterMatchRow');
  const noMatchMsg = document.getElementById('noFilterMatchMessage');
  const dailySearchInput = document.querySelector('[data-table-filter="dailyAttendanceTable"]');

  if (dailyTable && statusFilterTriggers.length > 0) {
    let currentFilter = 'all';

    function updateAttendanceFilter() {
      const rows = dailyTable.querySelectorAll('tbody tr:not(#noFilterMatchRow)');
      const searchQuery = dailySearchInput ? dailySearchInput.value.toLowerCase().trim() : '';
      let visibleCount = 0;

      rows.forEach(function (row) {
        const rowStatus = (row.getAttribute('data-status') || '').toLowerCase();
        const isLate = row.getAttribute('data-late') === 'true';
        const rowText = row.textContent.toLowerCase();

        // 1. Status matching
        let matchesStatus = false;
        if (currentFilter === 'all') {
          matchesStatus = true;
        } else if (currentFilter === 'unmarked') {
          matchesStatus = rowStatus === 'unmarked';
        } else if (currentFilter === 'present') {
          matchesStatus = rowStatus === 'present';
        } else if (currentFilter === 'absent') {
          matchesStatus = rowStatus === 'absent';
        } else if (currentFilter === 'half_day') {
          matchesStatus = rowStatus === 'half_day';
        } else if (currentFilter === 'incomplete') {
          matchesStatus = rowStatus === 'incomplete';
        } else if (currentFilter === 'late') {
          matchesStatus = isLate;
        } else {
          matchesStatus = rowStatus === currentFilter;
        }

        // 2. Search query matching
        const matchesSearch = !searchQuery || rowText.includes(searchQuery);

        if (matchesStatus && matchesSearch) {
          row.style.display = '';
          visibleCount++;
        } else {
          row.style.display = 'none';
        }
      });

      if (filterCountEl) {
        filterCountEl.textContent = visibleCount;
      }

      if (noMatchRow) {
        if (visibleCount === 0 && rows.length > 0) {
          noMatchRow.style.display = '';
          if (noMatchMsg) {
            let label = currentFilter;
            if (currentFilter === 'unmarked') label = 'Pending / Unmarked';
            else if (currentFilter === 'present') label = 'Present';
            else if (currentFilter === 'absent') label = 'Absent';
            else if (currentFilter === 'half_day') label = 'Half Day';
            else if (currentFilter === 'incomplete') label = 'Incomplete';
            else if (currentFilter === 'late') label = 'Late Arrivals';
            noMatchMsg.textContent = `No staff records found for status "${label}"${searchQuery ? ` matching "${searchQuery}"` : ''}.`;
          }
        } else {
          noMatchRow.style.display = 'none';
        }
      }

      // Update active visual state on filter buttons
      document.querySelectorAll('.filter-pill-btn').forEach(function (btn) {
        const btnFilter = btn.getAttribute('data-status-filter');
        if (btnFilter === currentFilter) {
          btn.classList.add('active');
          btn.classList.remove('btn-outline-secondary', 'btn-outline-warning', 'btn-outline-success', 'btn-outline-danger');
          if (btnFilter === 'unmarked') btn.classList.add('btn-warning');
          else if (btnFilter === 'present') btn.classList.add('btn-success');
          else if (btnFilter === 'absent') btn.classList.add('btn-danger');
          else btn.classList.add('btn-teal');
        } else {
          btn.classList.remove('active', 'btn-warning', 'btn-success', 'btn-danger', 'btn-teal');
          if (btnFilter === 'unmarked') btn.classList.add('btn-outline-warning');
          else if (btnFilter === 'present') btn.classList.add('btn-outline-success');
          else if (btnFilter === 'absent') btn.classList.add('btn-outline-danger');
          else btn.classList.add('btn-outline-secondary');
        }
      });

      // Update active visual state on stat cards
      statCards.forEach(function (card) {
        const cardFilter = card.getAttribute('data-status-filter');
        if (cardFilter === currentFilter) {
          card.classList.add('active-stat-card');
        } else {
          card.classList.remove('active-stat-card');
        }
      });
    }

    // Click handler for status filter triggers (pills and stat cards)
    document.addEventListener('click', function (e) {
      const trigger = e.target.closest('[data-status-filter]');
      if (!trigger) return;

      const requestedFilter = trigger.getAttribute('data-status-filter');
      if (!requestedFilter) return;

      e.preventDefault();
      // Clicking an already active stat-card resets back to 'all'
      if (trigger.classList.contains('stat-card') && currentFilter === requestedFilter) {
        currentFilter = 'all';
      } else {
        currentFilter = requestedFilter;
      }

      // Sync URL parameter (?status=...) without page reload
      try {
        const url = new URL(window.location.href);
        if (currentFilter === 'all') {
          url.searchParams.delete('status');
        } else {
          url.searchParams.set('status', currentFilter);
        }
        window.history.replaceState({}, '', url.toString());
      } catch (err) {
        // Fallback if URL API not supported
      }

      updateAttendanceFilter();
    });

    // Keyboard accessibility for stat cards (Enter or Space triggers filter)
    statCards.forEach(function (card) {
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          card.click();
        }
      });
    });

    // Search input coordinates with status filter
    if (dailySearchInput) {
      dailySearchInput.addEventListener('input', updateAttendanceFilter);
      dailySearchInput.addEventListener('keyup', updateAttendanceFilter);
    }

    // Initialize from URL parameter (?status=...)
    try {
      const initialUrl = new URL(window.location.href);
      const urlStatus = initialUrl.searchParams.get('status');
      if (urlStatus) {
        currentFilter = urlStatus.toLowerCase();
      }
    } catch (err) {}

    updateAttendanceFilter();
  }
});
