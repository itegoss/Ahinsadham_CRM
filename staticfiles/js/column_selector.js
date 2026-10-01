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
        buttonLabel: 'Select Columns',
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
          return {
            index: colIndex,
            key: key,
            label: label,
            alwaysVisible: isAction,
            defaultVisible: col.defaultVisible !== false
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

        return {
          index: colIndex,
          key: key,
          label: label,
          alwaysVisible: isAction,
          defaultVisible: true
        };
      });
    }

    /**
     * Loads saved visible keys from localStorage
     */
    _loadState() {
      try {
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

      // Badge in trigger button
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
        <button class="btn btn-sm col-selector-btn dropdown-toggle d-inline-flex align-items-center gap-1"
                type="button"
                data-bs-toggle="dropdown"
                data-bs-auto-close="outside"
                aria-expanded="false"
                title="Customize visible columns for this table">
          <i class="bi bi-columns-gap"></i>
          <span class="col-selector-btn-text">${this.options.buttonLabel}</span>
          <i class="bi bi-gear-fill col-gear-icon"></i>
          <span class="badge rounded-pill col-counter-badge ms-1">${count}/${total}</span>
        </button>

        <div class="dropdown-menu dropdown-menu-end col-selector-menu shadow-lg">
          <div class="col-selector-header p-2 border-bottom">
            <div class="d-flex align-items-center justify-content-between mb-2">
              <strong class="col-selector-title d-flex align-items-center gap-1">
                <i class="bi bi-layout-three-columns"></i>
                <span>Table Columns</span>
              </strong>
              <span class="badge bg-secondary-subtle text-secondary col-counter-text">${count} of ${total} visible</span>
            </div>

            <div class="col-selector-search-box mb-2">
              <div class="input-group input-group-sm">
                <span class="input-group-text bg-light border-end-0 py-1 px-2"><i class="bi bi-search text-muted"></i></span>
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
              const lockedBadge = col.alwaysVisible
                ? '<span class="badge bg-light text-secondary border ms-auto col-locked-badge" title="This column is required"><i class="bi bi-lock-fill me-1" style="font-size: 9px;"></i>Always Visible</span>'
                : '';

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
                    ${lockedBadge}
                  </div>
                </label>
              `;
            }).join('')}
          </div>

          <div class="col-selector-footer p-2 border-top bg-light text-center">
            <button type="button" class="btn btn-sm btn-outline-secondary w-100 col-reset-btn d-flex align-items-center justify-content-center gap-1">
              <i class="bi bi-arrow-counterclockwise"></i>
              <span>Reset Columns</span>
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

      // Prevent dropdown from closing when clicking inside menu on non-Bootstrap fallback
      const menu = wrapper.querySelector('.col-selector-menu');
      if (menu) {
        menu.addEventListener('click', (e) => {
          e.stopPropagation();
        });
      }

      // Reliable manual toggle fallback in case Bootstrap JS dropdown is not initialized
      const triggerBtn = wrapper.querySelector('.col-selector-btn');
      if (triggerBtn && menu) {
        triggerBtn.addEventListener('click', (e) => {
          // If bootstrap dropdown works naturally, this is harmless; if not, toggle manual class
          if (typeof bootstrap === 'undefined' || !bootstrap.Dropdown) {
            e.preventDefault();
            e.stopPropagation();
            const isOpen = menu.classList.contains('show');
            // Close all other col-selector menus
            document.querySelectorAll('.col-selector-menu.show').forEach(m => m.classList.remove('show'));
            if (!isOpen) {
              menu.classList.add('show');
            }
          }
        });
      }

    }
  }

  // Global document click to close manual fallback dropdowns
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.col-selector-wrapper')) {
      document.querySelectorAll('.col-selector-menu.show').forEach(m => m.classList.remove('show'));
    }
  });

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
