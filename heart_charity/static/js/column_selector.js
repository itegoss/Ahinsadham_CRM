/**
 * Ahinsadham CRM - Universal Reusable Table Column Selector Component
 * 
 * Provides independent column visibility selection, localStorage persistence,
 * multi-select dropdown popover, always-visible column protection (ACTIONS),
 * column search-cell sync, and reset functionality across all CRM data tables.
 */

(function (window, document) {
  'use strict';

  // Global registry for instances
  const instances = new Map();

  class TableColumnSelector {
    /**
     * @param {Object} options
     * @param {string|HTMLElement|NodeList} options.table - Target table element(s) or selector
     * @param {string|HTMLElement} options.container - Container element or selector for the dropdown button
     * @param {string} options.storageKey - Unique localStorage key (e.g. column_visibility_daanpeti_details)
     * @param {Array<Object>} [options.columns] - Optional column configurations [{key, label, alwaysVisible, defaultVisible}]
     * @param {string} [options.buttonLabel="Select Columns"] - Label for the trigger button
     * @param {Function} [options.onChange] - Callback fired when visibility changes
     */
    constructor(options) {
      if (!options || !options.storageKey) {
        console.error('TableColumnSelector: "storageKey" is required.');
        return;
      }
      this.options = Object.assign({
        buttonLabel: 'Select Column',
        columns: null,
        onChange: null
      }, options);

      this.storageKey = this.options.storageKey;
      this.safeKey = this.storageKey.replace(/[^a-zA-Z0-9_-]/g, '_');
      this.container = typeof this.options.container === 'string'
        ? document.querySelector(this.options.container)
        : this.options.container;

      this.tableSelector = typeof this.options.table === 'string' ? this.options.table : null;
      this.tables = this._resolveTables();

      if (!this.container) {
        console.warn(`TableColumnSelector: Container not found for key "${this.storageKey}".`);
        return;
      }

      // Initialize columns definition
      this.columns = this._resolveColumns();
      if (!this.columns || this.columns.length === 0) {
        console.warn(`TableColumnSelector: No columns found for key "${this.storageKey}".`);
        return;
      }

      // Load saved visibility state or default
      this.visibleKeys = this._loadState();

      // Render UI component
      this._renderUI();

      // Apply initial column visibility
      this.applyVisibility();

      // Register instance
      instances.set(this.storageKey, this);
    }

    /**
     * Resolves table elements associated with this selector
     */
    _resolveTables() {
      let elements = [];
      if (typeof this.options.table === 'string' && this.options.table !== 'auto') {
        try {
          elements = Array.from(document.querySelectorAll(this.options.table));
        } catch (e) {
          console.warn(`TableColumnSelector: Invalid table selector "${this.options.table}":`, e);
        }
      } else if ((typeof NodeList !== 'undefined' && this.options.table instanceof NodeList) || Array.isArray(this.options.table)) {
        elements = Array.from(this.options.table);
      } else if (typeof HTMLElement !== 'undefined' && this.options.table instanceof HTMLElement) {
        elements = [this.options.table];
      }


      // If no tables found yet and container exists, find tables within enclosing card or card-body
      if (elements.length === 0 && this.container) {
        const bodyCard = this.container.closest('.card-body');
        if (bodyCard) {
          const bodyTables = bodyCard.querySelectorAll('table');
          if (bodyTables.length > 0) elements = Array.from(bodyTables);
        }
        if (elements.length === 0) {
          const parentCard = this.container.closest('.card');
          if (parentCard) {
            const cardTables = parentCard.querySelectorAll('table');
            if (cardTables.length > 0) elements = Array.from(cardTables);
          }
        }
      }

      // Mark tables with data-colvis-id attribute for CSS targeting
      elements.forEach(table => {
        table.setAttribute('data-colvis-id', this.safeKey);
      });
      return elements;
    }


    /**
     * Refresh table references if DOM was updated dynamically
     */
    refreshTables() {
      this.tables = this._resolveTables();
      this.applyVisibility();
    }

    /**
     * Check if a column key or label represents an audit column
     */
    static isAuditColumn(key, label) {
      const normalizedKey = (key || '').toLowerCase().trim();
      const normalizedLabel = (label || '').toLowerCase().replace(/[\s_-]+/g, '_').trim();
      
      const auditKeys = [
        'created_by', 'created_on', 'created_at',
        'updated_by', 'updated_on', 'updated_at',
        'is_deleted',
        'deleted_by', 'deleted_on', 'deleted_at'
      ];

      return auditKeys.includes(normalizedKey) || auditKeys.includes(normalizedLabel);
    }

    /**
     * Resolves columns from options or auto-extracts from table headers
     */
    _resolveColumns() {
      // If explicit columns provided, use them
      if (Array.isArray(this.options.columns) && this.options.columns.length > 0) {
        return this.options.columns.map((col, index) => {
          const colIndex = index + 1; // 1-indexed for CSS :nth-child
          const key = col.key || `col_${colIndex}`;
          const label = (col.label || key).trim();
          const isAction = col.alwaysVisible === true || /^(actions?|action)$/i.test(label) || /^(actions?|action)$/i.test(key);
          const isAudit = TableColumnSelector.isAuditColumn(key, label);
          // Audit columns default to unselected (hidden) unless explicitly set otherwise
          const defaultVisible = col.defaultVisible !== undefined ? Boolean(col.defaultVisible) : (!isAudit);
          return {
            index: colIndex,
            key: key,
            label: label,
            alwaysVisible: isAction,
            isAudit: isAudit,
            defaultVisible: defaultVisible
          };
        });
      }

      // Auto-extract from the first matching table's thead
      const table = this.tables[0];
      if (!table) return [];

      const headerRow = table.querySelector('thead tr:first-child');
      if (!headerRow) return [];

      const thList = Array.from(headerRow.querySelectorAll('th'));
      return thList.map((th, index) => {
        const colIndex = index + 1;
        // Clean label: remove sort arrows and badges
        let label = th.innerText.replace(/[⬍▲▼↑↓]/g, '').trim();
        if (!label) {
          label = th.getAttribute('title') || `Column ${colIndex}`;
        }
        const key = th.getAttribute('data-col-key') || th.getAttribute('data-col') || `col_${colIndex}`;
        const isAction = /^(actions?|action)$/i.test(label) || /^(actions?|action)$/i.test(key) || th.classList.contains('col-always-visible');
        const isAudit = TableColumnSelector.isAuditColumn(key, label);

        return {
          index: colIndex,
          key: key,
          label: label,
          alwaysVisible: isAction,
          isAudit: isAudit,
          defaultVisible: !isAudit
        };
      });
    }

    /**
     * Loads saved visible keys from localStorage
     */
    _loadState() {
      const SCHEMA_VERSION = 'v2_audit_hidden';
      const versionKey = `${this.storageKey}__schema_ver`;
      const currentVer = localStorage.getItem(versionKey);

      try {
        // Migration: If table hasn't migrated yet, clear old stored state so audit columns default to unselected
        if (currentVer !== SCHEMA_VERSION) {
          localStorage.removeItem(this.storageKey);
          localStorage.setItem(versionKey, SCHEMA_VERSION);
          return this.columns
            .filter(c => c.defaultVisible !== false || c.alwaysVisible)
            .map(c => c.key);
        }

        const raw = localStorage.getItem(this.storageKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed) && parsed.length > 0) {
            const set = new Set(parsed);
            // Ensure alwaysVisible columns are permanently included
            this.columns.forEach(col => {
              if (col.alwaysVisible) set.add(col.key);
            });
            return Array.from(set);
          }
        }
      } catch (e) {
        console.warn(`TableColumnSelector: Error reading localStorage for "${this.storageKey}":`, e);
      }

      // Default: all defaultVisible columns (and alwaysVisible)
      return this.columns
        .filter(c => c.defaultVisible !== false || c.alwaysVisible)
        .map(c => c.key);
    }

    /**
     * Saves current visible keys to localStorage
     */
    _saveState() {
      try {
        const SCHEMA_VERSION = 'v2_audit_hidden';
        const versionKey = `${this.storageKey}__schema_ver`;
        localStorage.setItem(versionKey, SCHEMA_VERSION);
        localStorage.setItem(this.storageKey, JSON.stringify(this.visibleKeys));
      } catch (e) {
        console.warn(`TableColumnSelector: Error saving to localStorage for "${this.storageKey}":`, e);
      }
    }

    /**
     * Clears localStorage and resets to default configuration
     */
    reset() {
      try {
        localStorage.removeItem(this.storageKey);
      } catch (e) {
        console.warn(`TableColumnSelector: Error clearing localStorage for "${this.storageKey}":`, e);
      }

      this.visibleKeys = this.columns
        .filter(c => c.defaultVisible !== false || c.alwaysVisible)
        .map(c => c.key);

      this._saveState();
      this._updateUIState();
      this.applyVisibility();

      if (typeof this.options.onChange === 'function') {
        this.options.onChange(this.visibleKeys);
      }
    }

    /**
     * Select / show all columns
     */
    selectAll() {
      this.visibleKeys = this.columns.map(c => c.key);
      this._saveState();
      this._updateUIState();
      this.applyVisibility();

      if (typeof this.options.onChange === 'function') {
        this.options.onChange(this.visibleKeys);
      }
    }

    /**
     * Toggles visibility for a specific column key
     */
    toggleColumn(key, isVisible) {
      const col = this.columns.find(c => c.key === key);
      if (!col) return;

      // Always visible columns cannot be unchecked
      if (col.alwaysVisible) {
        if (!this.visibleKeys.includes(key)) {
          this.visibleKeys.push(key);
        }
        return;
      }

      if (isVisible) {
        if (!this.visibleKeys.includes(key)) {
          this.visibleKeys.push(key);
        }
      } else {
        this.visibleKeys = this.visibleKeys.filter(k => k !== key);
      }

      this._saveState();
      this._updateUIState();
      this.applyVisibility();

      if (typeof this.options.onChange === 'function') {
        this.options.onChange(this.visibleKeys);
      }
    }

    /**
     * Injects / updates dynamic scoped CSS style to hide unselected columns
     */
    applyVisibility() {
      let styleEl = document.getElementById(`colvis-style-${this.safeKey}`);
      if (!styleEl) {
        styleEl = document.createElement('style');
        styleEl.id = `colvis-style-${this.safeKey}`;
        document.head.appendChild(styleEl);
      }

      const hiddenCols = this.columns.filter(c => !this.visibleKeys.includes(c.key));

      if (hiddenCols.length === 0) {
        styleEl.textContent = '';
        return;
      }

      // Generate CSS selectors for each hidden column
      // Hides both the th in thead row 1, td/th in column search row, and td in tbody
      // Preserves full-width rows with colspan (e.g. "No records found")
      const rules = hiddenCols.map(c => {
        return `[data-colvis-id="${this.safeKey}"] tr > th:nth-child(${c.index}),
[data-colvis-id="${this.safeKey}"] tr > td:not([colspan]):nth-child(${c.index}) {
  display: none !important;
}`;
      });

      styleEl.textContent = rules.join('\n');
    }

    /**
     * Updates button badge counter, header text, and checkbox states
     */
    _updateUIState() {
      if (!this.wrapper) return;

      const total = this.columns.length;
      const count = this.visibleKeys.length;

      // Update title on trigger button
      const triggerBtn = this.wrapper.querySelector('.col-selector-btn');
      if (triggerBtn) {
        triggerBtn.title = `Select Columns (${count}/${total} visible)`;
      }

      // Badge in trigger button (if present)
      const badge = this.wrapper.querySelector('.col-counter-badge');
      if (badge) {
        badge.textContent = `${count}/${total}`;
        badge.title = `${count} of ${total} columns visible`;
      }

      // Text in dropdown header
      const counterText = this.wrapper.querySelector('.col-counter-text');
      if (counterText) {
        counterText.textContent = `${count} of ${total} visible`;
      }

      // Checkbox checked state
      const checkboxes = this.wrapper.querySelectorAll('.col-toggle-checkbox');
      checkboxes.forEach(cb => {
        const key = cb.getAttribute('data-col-key');
        const col = this.columns.find(c => c.key === key);
        if (col && col.alwaysVisible) {
          cb.checked = true;
          cb.disabled = true;
        } else {
          cb.checked = this.visibleKeys.includes(key);
        }
      });
    }

    /**
     * Builds and renders the complete dropdown DOM
     */
    _renderUI() {
      this.container.innerHTML = '';

      const wrapper = document.createElement('div');
      wrapper.className = 'dropdown col-selector-wrapper d-inline-block';
      this.wrapper = wrapper;

      const total = this.columns.length;
      const count = this.visibleKeys.length;

      wrapper.innerHTML = `
        <button class="btn btn-sm col-selector-btn d-inline-flex align-items-center justify-content-center"
                type="button"
                data-bs-toggle="dropdown"
                data-bs-display="static"
                data-bs-auto-close="outside"
                aria-expanded="false"
                title="Select Columns (${count}/${total} visible)">
          <i class="bi bi-columns-gap"></i>
        </button>

        <div class="dropdown-menu dropdown-menu-end col-selector-menu shadow-lg">
          <div class="col-selector-header p-2 border-bottom">
            <div class="d-flex align-items-center justify-content-between mb-2">
              <strong class="col-selector-title d-flex align-items-center gap-1">
                <i class="bi bi-layout-three-columns"></i>
                <span>Table Columns</span>
              </strong>
              <div class="d-flex align-items-center gap-2">
                <span class="badge bg-secondary-subtle text-secondary col-counter-text">${count} of ${total} visible</span>
                <button type="button" class="btn-close col-selector-close-btn" aria-label="Close" title="Close" style="font-size: 0.72rem; cursor: pointer;"></button>
              </div>
            </div>

            <div class="col-selector-search-box mb-2">
              <div class="input-group input-group-sm">
                <input type="text" class="form-control form-control-sm border-start-0 col-search-input py-1" placeholder="Find column...">
              </div>
            </div>

            <div class="d-flex align-items-center justify-content-between pt-1">
              <button type="button" class="btn btn-link btn-xs p-0 text-decoration-none col-select-all-btn">
                <i class="bi bi-check2-all me-1"></i>Select All
              </button>
              <button type="button" class="btn btn-link btn-xs p-0 text-decoration-none text-danger col-reset-btn" title="Reset to default columns">
                <i class="bi bi-arrow-counterclockwise me-1"></i>Reset Columns
              </button>
            </div>
          </div>

          <div class="col-selector-body p-1" style="max-height: 280px; overflow-y: auto;">
            ${this.columns.map(col => {
        const isChecked = col.alwaysVisible || this.visibleKeys.includes(col.key);
        const isDisabled = col.alwaysVisible ? 'disabled' : '';
        const extraBadge = col.alwaysVisible
          ? '<span class="badge bg-light text-secondary border ms-auto col-locked-badge" title="This column is required"><i class="bi bi-lock-fill me-1" style="font-size: 9px;"></i>Always Visible</span>'
          : (col.isAudit ? '<span class="badge bg-light text-secondary border ms-auto col-audit-badge" style="font-size: 9px;" title="Audit Column"><i class="bi bi-clock-history me-1" style="font-size: 9px;"></i>Audit</span>' : '');

        return `
                <label class="dropdown-item d-flex align-items-center justify-content-between py-1 px-2 rounded col-checkbox-item ${col.alwaysVisible ? 'col-item-locked' : ''}">
                  <div class="form-check d-flex align-items-center gap-2 mb-0 w-100">
                    <input class="form-check-input col-toggle-checkbox m-0"
                           type="checkbox"
                           data-col-key="${col.key}"
                           id="col_cb_${this.safeKey}_${col.key}"
                           ${isChecked ? 'checked' : ''}
                           ${isDisabled}>
                    <span class="form-check-label text-truncate" for="col_cb_${this.safeKey}_${col.key}" title="${col.label}">
                      ${col.label}
                    </span>
                    ${extraBadge}
                  </div>
                </label>
              `;
      }).join('')}
          </div>

          <div class="col-selector-footer p-2 border-top bg-light d-flex gap-2">
            <button type="button" class="btn btn-sm btn-outline-secondary flex-grow-1 col-reset-btn d-flex align-items-center justify-content-center gap-1">
              <i class="bi bi-arrow-counterclockwise"></i>
              <span>Reset</span>
            </button>
            <button type="button" class="btn btn-sm btn-success flex-grow-1 col-apply-btn d-flex align-items-center justify-content-center gap-1">
              <i class="bi bi-check2"></i>
              <span>Apply</span>
            </button>
          </div>
        </div>
      `;

      this.container.appendChild(wrapper);

      // Event Listeners
      const searchInput = wrapper.querySelector('.col-search-input');
      const items = wrapper.querySelectorAll('.col-checkbox-item');

      // Live search columns filter inside dropdown
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const query = e.target.value.toLowerCase().trim();
          items.forEach(item => {
            const text = item.innerText.toLowerCase();
            item.style.display = text.includes(query) ? 'flex' : 'none';
          });
        });
      }

      // Checkbox changes
      wrapper.querySelectorAll('.col-toggle-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
          const key = e.target.getAttribute('data-col-key');
          this.toggleColumn(key, e.target.checked);
        });
      });

      // Quick action: Select All
      const selectAllBtn = wrapper.querySelector('.col-select-all-btn');
      if (selectAllBtn) {
        selectAllBtn.addEventListener('click', (e) => {
          e.preventDefault();
          this.selectAll();
        });
      }

      // Reset buttons
      wrapper.querySelectorAll('.col-reset-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          this.reset();
        });
      });

      // Close / Apply buttons & backdrop logic
      const closeColMenu = () => {
        menu.classList.remove('show');
        wrapper.classList.remove('show');
        triggerBtn.classList.remove('show');
        triggerBtn.setAttribute('aria-expanded', 'false');
        TableColumnSelector._removeBackdrop();
        if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
          const inst = bootstrap.Dropdown.getInstance(triggerBtn);
          if (inst) inst.hide();
        }
      };

      wrapper.querySelectorAll('.col-selector-close-btn, .col-apply-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          closeColMenu();
        });
      });

      // Prevent dropdown from closing when clicking inside menu
      const menu = wrapper.querySelector('.col-selector-menu');
      if (menu) {
        menu.addEventListener('click', (e) => {
          e.stopPropagation();
        });
      }

      // Bootstrap dropdown event hooks
      wrapper.addEventListener('show.bs.dropdown', () => {
        wrapper.classList.add('show');
        if (menu) {
          menu.style.removeProperty('transform');
          menu.style.removeProperty('inset');
        }
        const sc = wrapper.closest('.search-container, .gcp-table-toolbar');
        if (sc) sc.style.setProperty('z-index', '1055', 'important');
        wrapper.style.setProperty('z-index', '1055', 'important');
      });

      wrapper.addEventListener('shown.bs.dropdown', () => {
        if (menu) {
          menu.style.removeProperty('transform');
          menu.style.removeProperty('inset');
        }
      });

      wrapper.addEventListener('hidden.bs.dropdown', () => {
        wrapper.classList.remove('show');
        const sc = wrapper.closest('.search-container, .gcp-table-toolbar');
        if (sc) sc.style.removeProperty('z-index');
        wrapper.style.removeProperty('z-index');
      });

      const triggerBtn = wrapper.querySelector('.col-selector-btn');
      if (triggerBtn) {
        // Reliable toggle fallback in case Bootstrap JS dropdown is not initialized
        triggerBtn.addEventListener('click', (e) => {
          if (typeof bootstrap === 'undefined' || !bootstrap.Dropdown) {
            e.preventDefault();
            e.stopPropagation();
            const isOpen = menu.classList.contains('show');
            TableColumnSelector.closeAll();
            if (!isOpen) {
              menu.classList.add('show');
              wrapper.classList.add('show');
              triggerBtn.classList.add('show');
              triggerBtn.setAttribute('aria-expanded', 'true');
              const sc = wrapper.closest('.search-container, .gcp-table-toolbar');
              if (sc) sc.style.setProperty('z-index', '1055', 'important');
              wrapper.style.setProperty('z-index', '1055', 'important');
            }
          }
        });
      }

    }
  }

  // Global document click to close manual fallback dropdowns
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.col-selector-wrapper')) {
      TableColumnSelector.closeAll();
    }
  });

  TableColumnSelector._ensureBackdrop = function () {
    // Backdrop removed: dropdown is cleanly anchored directly below the button
  };

  TableColumnSelector._removeBackdrop = function () {
    const bd = document.querySelector('.col-selector-backdrop');
    if (bd) bd.remove();
  };

  TableColumnSelector.closeAll = function () {
    document.querySelectorAll('.col-selector-menu.show').forEach(m => m.classList.remove('show'));
    document.querySelectorAll('.col-selector-wrapper.show').forEach(w => {
      w.classList.remove('show');
      w.style.removeProperty('z-index');
      const sc = w.closest('.search-container, .gcp-table-toolbar');
      if (sc) sc.style.removeProperty('z-index');
    });
    document.querySelectorAll('.col-selector-btn.show').forEach(b => {
      b.classList.remove('show');
      b.setAttribute('aria-expanded', 'false');
    });
    TableColumnSelector._removeBackdrop();
  };

  // Export to window
  window.TableColumnSelector = TableColumnSelector;
  window.ColumnSelector = TableColumnSelector;

  /**
   * Helper to initialize column selector on elements with data-colvis-mount
   */
  TableColumnSelector.initAll = function () {
    const mounts = document.querySelectorAll('[data-colvis-mount]');
    mounts.forEach(mount => {
      const storageKey = mount.getAttribute('data-storage-key');
      const tableSelector = mount.getAttribute('data-table');
      if (storageKey && tableSelector && !instances.has(storageKey)) {
        new TableColumnSelector({
          container: mount,
          table: tableSelector,
          storageKey: storageKey
        });
      }
    });
  };

})(window, document);
