/**
 * Dynamic Dependent Country, State, and City Dropdowns
 * Powered by CountriesNow API (https://countriesnow.space/api/v0.1/countries)
 */
(function (window, document) {
    'use strict';

    // In-memory cache for fast lookups during the session
    const cache = {
        countries: null,
        states: {},
        cities: {}
    };

    const API_BASE = 'https://countriesnow.space/api/v0.1/countries';

    /**
     * Safe SessionStorage helper with in-memory fallback
     */
    function getStored(key) {
        try {
            const item = sessionStorage.getItem(key);
            return item ? JSON.parse(item) : null;
        } catch (e) {
            return null;
        }
    }

    function setStored(key, value) {
        try {
            sessionStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            // Ignore quota or private browsing errors
        }
    }

    /**
     * Trigger change event safely (supporting vanilla and Select2 if present)
     */
    function triggerChange(el) {
        if (!el) return;
        const evt = new Event('change', { bubbles: true });
        el.dispatchEvent(evt);
        if (window.jQuery && window.jQuery(el).data('select2')) {
            window.jQuery(el).trigger('change.select2');
        }
    }

    /**
     * Fetch list of all countries
     */
    async function fetchCountries() {
        if (cache.countries && cache.countries.length > 0) {
            return cache.countries;
        }
        const stored = getStored('csc_countries_cache');
        if (stored && Array.isArray(stored) && stored.length > 0) {
            cache.countries = stored;
            return stored;
        }

        let countriesList = [];

        // Try /iso first (lightweight: ~8KB vs ~2.8MB)
        try {
            const resp = await fetch(`${API_BASE}/iso`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' }
            });
            if (resp.ok) {
                const json = await resp.json();
                if (!json.error && Array.isArray(json.data)) {
                    countriesList = json.data
                        .map(item => (item.name || '').trim())
                        .filter(Boolean);
                }
            }
        } catch (err) {
            console.warn('CountriesNow /iso fetch failed, trying fallback...', err);
        }

        // Fallback to /countries if /iso failed or returned empty
        if (countriesList.length === 0) {
            try {
                const resp = await fetch(API_BASE, {
                    method: 'GET',
                    headers: { 'Accept': 'application/json' }
                });
                if (resp.ok) {
                    const json = await resp.json();
                    if (!json.error && Array.isArray(json.data)) {
                        countriesList = json.data
                            .map(item => (item.country || item.name || '').trim())
                            .filter(Boolean);
                    }
                }
            } catch (err) {
                console.error('CountriesNow countries fallback failed:', err);
            }
        }

        // Deduplicate and sort alphabetically
        const unique = Array.from(new Set(countriesList)).sort((a, b) => a.localeCompare(b));
        if (unique.length > 0) {
            cache.countries = unique;
            setStored('csc_countries_cache', unique);
            return unique;
        }

        throw new Error('Unable to load countries list');
    }

    /**
     * Fetch states for a given country
     */
    async function fetchStates(country) {
        if (!country) return [];
        const cacheKey = `csc_states_${country}`;

        if (cache.states[country]) {
            return cache.states[country];
        }
        const stored = getStored(cacheKey);
        if (stored && Array.isArray(stored)) {
            cache.states[country] = stored;
            return stored;
        }

        try {
            const resp = await fetch(`${API_BASE}/states`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ country: country })
            });

            if (resp.ok) {
                const json = await resp.json();
                if (!json.error && json.data && Array.isArray(json.data.states)) {
                    const states = json.data.states
                        .map(s => (s.name || '').trim())
                        .filter(Boolean);
                    const unique = Array.from(new Set(states)).sort((a, b) => a.localeCompare(b));
                    cache.states[country] = unique;
                    setStored(cacheKey, unique);
                    return unique;
                }
            }
        } catch (err) {
            console.error(`CountriesNow fetch states failed for ${country}:`, err);
        }

        return [];
    }

    /**
     * Fetch cities for a given country and state
     */
    async function fetchCities(country, state) {
        if (!country || !state) return [];
        const cacheKey = `csc_cities_${country}_${state}`;

        if (cache.cities[cacheKey]) {
            return cache.cities[cacheKey];
        }
        const stored = getStored(cacheKey);
        if (stored && Array.isArray(stored)) {
            cache.cities[cacheKey] = stored;
            return stored;
        }

        try {
            const resp = await fetch(`${API_BASE}/state/cities`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ country: country, state: state })
            });

            if (resp.ok) {
                const json = await resp.json();
                if (!json.error && Array.isArray(json.data)) {
                    const cities = json.data
                        .map(c => (c || '').trim())
                        .filter(Boolean);
                    const unique = Array.from(new Set(cities)).sort((a, b) => a.localeCompare(b));
                    cache.cities[cacheKey] = unique;
                    setStored(cacheKey, unique);
                    return unique;
                }
            }
        } catch (err) {
            console.error(`CountriesNow fetch cities failed for ${country}, ${state}:`, err);
        }

        return [];
    }

    /**
     * Helper to set options in a select element
     */
    function setSelectOptions(selectEl, placeholder, items, selectedValue, disabled = false) {
        selectEl.innerHTML = '';

        const defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = placeholder;
        selectEl.appendChild(defaultOpt);

        let matchFound = false;
        if (Array.isArray(items)) {
            items.forEach(item => {
                const opt = document.createElement('option');
                opt.value = item;
                opt.textContent = item;
                if (selectedValue && item.toLowerCase() === selectedValue.trim().toLowerCase()) {
                    opt.selected = true;
                    matchFound = true;
                }
                selectEl.appendChild(opt);
            });
        }

        // Preserve saved/existing database value if not returned by API
        if (selectedValue && !matchFound && selectedValue.trim() !== '' && selectedValue !== '__other__') {
            const customOpt = document.createElement('option');
            customOpt.value = selectedValue;
            customOpt.textContent = selectedValue;
            customOpt.selected = true;
            selectEl.appendChild(customOpt);
            matchFound = true;
        }

        // Add manual entry option if list is not empty
        if (items && items.length > 0) {
            const otherOpt = document.createElement('option');
            otherOpt.value = '__other__';
            otherOpt.textContent = 'Other / Not Listed...';
            selectEl.appendChild(otherOpt);
        }

        selectEl.disabled = disabled;
    }

    /**
     * Main initializer for dynamic dropdowns on a form
     */
    function setupDynamicCountryStateCity(config) {
        const countryId = config.countryId || 'country';
        const stateId = config.stateId || 'state';
        const cityId = config.cityId || 'city';

        const countryEl = document.getElementById(countryId);
        const stateEl = document.getElementById(stateId);
        const cityEl = document.getElementById(cityId);

        if (!countryEl || !stateEl || !cityEl) {
            return;
        }

        // Mark as initialized to prevent double-setup
        if (countryEl.dataset.cscInitialized === 'true') {
            return;
        }
        countryEl.dataset.cscInitialized = 'true';

        // Read pre-selected values from data attributes, config, or current element value
        let initialCountry = config.initialCountry ||
                             countryEl.getAttribute('data-selected-country') ||
                             (countryEl.value && countryEl.value !== 'Other' ? countryEl.value : '') || '';
        let initialState = config.initialState ||
                           stateEl.getAttribute('data-selected-state') ||
                           stateEl.value || '';
        let initialCity = config.initialCity ||
                          cityEl.getAttribute('data-selected-city') ||
                          cityEl.value || '';

        // Clean initial values
        initialCountry = initialCountry.trim();
        initialState = initialState.trim();
        initialCity = initialCity.trim();

        // Fallback textbox containers if present
        const stateDropdownBox = document.getElementById(config.stateDropdownBoxId || 'stateDropdownBox');
        const stateTextboxBox = document.getElementById(config.stateTextboxBoxId || 'stateTextboxBox');
        const stateText = document.getElementById(config.stateTextId || 'state_text');

        function showStateDropdown() {
            if (stateDropdownBox) stateDropdownBox.style.display = 'block';
            if (stateTextboxBox) stateTextboxBox.style.display = 'none';
        }

        function showStateTextbox() {
            if (stateDropdownBox) stateDropdownBox.style.display = 'none';
            if (stateTextboxBox) stateTextboxBox.style.display = 'block';
        }

        // Load cities for a selected state
        async function loadCities(country, state, targetCity) {
            if (!country || !state || state === '__other__') {
                setSelectOptions(cityEl, 'Select State first', [], '', true);
                return;
            }

            // Show loading indicator
            setSelectOptions(cityEl, 'Loading cities...', [], '', true);

            try {
                const cities = await fetchCities(country, state);

                if (cities.length === 0) {
                    // No cities in API for this state
                    cityEl.innerHTML = '';
                    const defaultOpt = document.createElement('option');
                    defaultOpt.value = '';
                    defaultOpt.textContent = 'No cities available (enter manually)';
                    cityEl.appendChild(defaultOpt);

                    if (targetCity) {
                        const opt = document.createElement('option');
                        opt.value = targetCity;
                        opt.textContent = targetCity;
                        opt.selected = true;
                        cityEl.appendChild(opt);
                    }

                    const otherOpt = document.createElement('option');
                    otherOpt.value = '__other__';
                    otherOpt.textContent = 'Enter City Manually...';
                    cityEl.appendChild(otherOpt);

                    cityEl.disabled = false;
                } else {
                    setSelectOptions(cityEl, 'Select City', cities, targetCity, false);
                }
            } catch (err) {
                console.error('Error in loadCities:', err);
                setSelectOptions(cityEl, 'Error loading cities (Click to enter manually)', [], targetCity, false);
            }
        }

        // Load states for a selected country
        async function loadStates(country, targetState, targetCity) {
            if (!country) {
                setSelectOptions(stateEl, 'Select Country first', [], '', true);
                setSelectOptions(cityEl, 'Select State first', [], '', true);
                showStateDropdown();
                return;
            }

            // Show loading indicator
            setSelectOptions(stateEl, 'Loading states...', [], '', true);
            setSelectOptions(cityEl, 'Select State first', [], '', true);

            try {
                const states = await fetchStates(country);

                if (states.length === 0) {
                    // Country has no states or API failed
                    if (stateTextboxBox && stateDropdownBox) {
                        showStateTextbox();
                        if (targetState && stateText) {
                            stateText.value = targetState;
                        }
                    } else {
                        showStateDropdown();
                        stateEl.innerHTML = '';
                        const defaultOpt = document.createElement('option');
                        defaultOpt.value = '';
                        defaultOpt.textContent = 'No states found (enter manually)';
                        stateEl.appendChild(defaultOpt);

                        if (targetState) {
                            const opt = document.createElement('option');
                            opt.value = targetState;
                            opt.textContent = targetState;
                            opt.selected = true;
                            stateEl.appendChild(opt);
                        }

                        const otherOpt = document.createElement('option');
                        otherOpt.value = '__other__';
                        otherOpt.textContent = 'Enter State Manually...';
                        stateEl.appendChild(otherOpt);
                        stateEl.disabled = false;
                    }

                    // Enable city or load cities
                    if (targetState) {
                        await loadCities(country, targetState, targetCity);
                    } else {
                        setSelectOptions(cityEl, 'Select State first', [], '', true);
                    }
                } else {
                    showStateDropdown();
                    setSelectOptions(stateEl, 'Select State', states, targetState, false);

                    if (targetState) {
                        await loadCities(country, targetState, targetCity);
                    }
                }
            } catch (err) {
                console.error('Error in loadStates:', err);
                setSelectOptions(stateEl, 'Error loading states (click to retry)', [], targetState, false);
            }
        }

        // Handle State change
        stateEl.addEventListener('change', function () {
            const selectedVal = this.value;
            if (selectedVal === '__other__') {
                const manual = window.prompt('Enter your state name:');
                if (manual && manual.trim()) {
                    const trimmed = manual.trim();
                    const opt = document.createElement('option');
                    opt.value = trimmed;
                    opt.textContent = trimmed;
                    opt.selected = true;
                    stateEl.insertBefore(opt, stateEl.lastChild);
                    stateEl.value = trimmed;
                    loadCities(countryEl.value, trimmed, null);
                } else {
                    stateEl.value = '';
                    setSelectOptions(cityEl, 'Select State first', [], '', true);
                }
            } else if (selectedVal) {
                loadCities(countryEl.value, selectedVal, null);
            } else {
                setSelectOptions(cityEl, 'Select State first', [], '', true);
            }
        });

        // Handle City change
        cityEl.addEventListener('change', function () {
            if (this.value === '__other__') {
                const manual = window.prompt('Enter your city name:');
                if (manual && manual.trim()) {
                    const trimmed = manual.trim();
                    const opt = document.createElement('option');
                    opt.value = trimmed;
                    opt.textContent = trimmed;
                    opt.selected = true;
                    cityEl.insertBefore(opt, cityEl.lastChild);
                    cityEl.value = trimmed;
                } else {
                    cityEl.value = '';
                }
            }
        });

        // Handle Country change
        countryEl.addEventListener('change', function () {
            const country = this.value;
            if (country) {
                loadStates(country, null, null);
            } else {
                setSelectOptions(stateEl, 'Select Country first', [], '', true);
                setSelectOptions(cityEl, 'Select State first', [], '', true);
            }
        });

        // Initial setup: Load countries
        (async function init() {
            setSelectOptions(countryEl, 'Loading countries...', [], initialCountry, true);
            if (!initialCountry) {
                setSelectOptions(stateEl, 'Select Country first', [], '', true);
                setSelectOptions(cityEl, 'Select State first', [], '', true);
            }

            try {
                const countries = await fetchCountries();
                setSelectOptions(countryEl, 'Select Country', countries, initialCountry, false);

                if (initialCountry) {
                    await loadStates(initialCountry, initialState, initialCity);
                }
            } catch (err) {
                console.error('Error initializing countries:', err);
                setSelectOptions(countryEl, 'Error loading countries (Click to retry)', [], initialCountry, false);
                countryEl.addEventListener('click', function retryHandler() {
                    if (countryEl.options.length <= 1) {
                        countryEl.removeEventListener('click', retryHandler);
                        init();
                    }
                });
            }
        })();
    }

    // Auto-detect and run on DOM ready
    function autoInit() {
        if (document.getElementById('country') && document.getElementById('state') && document.getElementById('city')) {
            setupDynamicCountryStateCity({
                countryId: 'country',
                stateId: 'state',
                cityId: 'city'
            });
        }
        if (document.getElementById('id_country') && document.getElementById('id_state') && document.getElementById('id_city')) {
            setupDynamicCountryStateCity({
                countryId: 'id_country',
                stateId: 'id_state',
                cityId: 'id_city'
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }

    // Export globally for explicit initialization if needed
    window.setupDynamicCountryStateCity = setupDynamicCountryStateCity;

})(window, document);

