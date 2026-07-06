/**
 * منتقي موقع HR — خريطة Leaflet + GPS + عنوان فعلي من الخادم.
 */
(function () {
    'use strict';

    var DEFAULT_LAT = 24.7136;
    var DEFAULT_LNG = 46.6753;
    var LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    var LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';

    function loadStylesheet(href) {
        return new Promise(function (resolve, reject) {
            if (document.querySelector('link[data-hr-leaflet]')) {
                resolve();
                return;
            }
            var link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.setAttribute('data-hr-leaflet', '1');
            link.onload = function () { resolve(); };
            link.onerror = function () { reject(new Error('leaflet-css')); };
            document.head.appendChild(link);
        });
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            if (window.L) {
                resolve();
                return;
            }
            if (document.querySelector('script[data-hr-leaflet]')) {
                var wait = setInterval(function () {
                    if (window.L) {
                        clearInterval(wait);
                        resolve();
                    }
                }, 50);
                setTimeout(function () {
                    clearInterval(wait);
                    if (window.L) resolve();
                    else reject(new Error('leaflet-js-timeout'));
                }, 10000);
                return;
            }
            var script = document.createElement('script');
            script.src = src;
            script.defer = true;
            script.setAttribute('data-hr-leaflet', '1');
            script.onload = function () { resolve(); };
            script.onerror = function () { reject(new Error('leaflet-js')); };
            document.head.appendChild(script);
        });
    }

    function ensureLeaflet() {
        return loadStylesheet(LEAFLET_CSS).then(function () {
            return loadScript(LEAFLET_JS);
        });
    }

    function mapsUrl(lat, lng) {
        return 'https://www.google.com/maps?q=' + lat.toFixed(6) + ',' + lng.toFixed(6);
    }

    function parseStoredLocation(value) {
        var v = (value || '').trim();
        if (!v) {
            return { text: '', lat: null, lng: null };
        }
        var sep = ' | ';
        var idx = v.indexOf(sep);
        if (idx > -1) {
            var tail = v.slice(idx + sep.length).trim();
            var m = tail.match(/q=(-?\d+\.?\d*),(-?\d+\.?\d*)/);
            if (m) {
                return {
                    text: v.slice(0, idx).trim(),
                    lat: parseFloat(m[1]),
                    lng: parseFloat(m[2]),
                };
            }
        }
        var direct = v.match(/q=(-?\d+\.?\d*),(-?\d+\.?\d*)/);
        if (direct) {
            return { text: '', lat: parseFloat(direct[1]), lng: parseFloat(direct[2]) };
        }
        return { text: v, lat: null, lng: null };
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function reverseGeocode(lat, lng, geocodeUrl) {
        if (!geocodeUrl) {
            return Promise.reject(new Error('no-geocode-url'));
        }
        var url = geocodeUrl + '?lat=' + encodeURIComponent(lat) + '&lng=' + encodeURIComponent(lng);
        return fetch(url, {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                Accept: 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(),
            },
        })
            .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
            .then(function (res) {
                if (!res.ok || !res.body || !res.body.success) {
                    throw new Error((res.body && res.body.message) || 'تعذّر جلب العنوان');
                }
                return res.body.data || {};
            })
            .then(function (data) {
                return (data.address || '').trim();
            });
    }

    function coordsFallback(lat, lng) {
        return 'الإحداثيات: ' + lat.toFixed(5) + '، ' + lng.toFixed(5);
    }

    function buildLocationPicker() {
        return {
            mapOpen: false,
            loading: false,
            geoLoading: false,
            lat: DEFAULT_LAT,
            lng: DEFAULT_LNG,
            hasCoords: false,
            address: '',
            statusMsg: '',
            geocodeUrl: '',
            inputEl: null,
            latField: null,
            lngField: null,
            map: null,
            marker: null,

            init: function () {
                this.geocodeUrl = this.$el.dataset.geocodeUrl || '';
                this.inputEl = this.$el.querySelector('input[type="text"][name="location"]');
                this.latField = this.$el.querySelector('input[name="location_lat"]');
                this.lngField = this.$el.querySelector('input[name="location_lng"]');
                if (!this.inputEl) return;

                var parsed = parseStoredLocation(this.inputEl.value);
                if (parsed.text) {
                    this.inputEl.value = parsed.text;
                    this.address = parsed.text;
                }
                if (parsed.lat != null && parsed.lng != null) {
                    this.lat = parsed.lat;
                    this.lng = parsed.lng;
                    this.hasCoords = true;
                    this.syncHiddenCoords();
                }
            },

            syncHiddenCoords: function () {
                if (this.latField) {
                    this.latField.value = this.hasCoords ? this.lat.toFixed(6) : '';
                }
                if (this.lngField) {
                    this.lngField.value = this.hasCoords ? this.lng.toFixed(6) : '';
                }
            },

            syncInputFromAddress: function () {
                if (!this.inputEl) return;
                var addr = (this.address || '').trim();
                if (addr) {
                    this.inputEl.value = addr;
                }
            },

            applyResolvedAddress: function (addr) {
                this.address = addr || coordsFallback(this.lat, this.lng);
                this.syncInputFromAddress();
                this.syncHiddenCoords();
            },

            resolveAddress: function (lat, lng) {
                var self = this;
                this.loading = true;
                this.statusMsg = '';
                return reverseGeocode(lat, lng, this.geocodeUrl)
                    .then(function (addr) {
                        self.applyResolvedAddress(addr);
                        return addr;
                    })
                    .catch(function () {
                        self.applyResolvedAddress(coordsFallback(lat, lng));
                        self.statusMsg = 'تعذّر جلب العنوان التفصيلي — تم حفظ الإحداثيات.';
                        return '';
                    })
                    .finally(function () {
                        self.loading = false;
                    });
            },

            openMap: function () {
                var self = this;
                this.mapOpen = true;
                this.statusMsg = '';
                this.$nextTick(function () {
                    ensureLeaflet().then(function () {
                        self.initMap();
                    }).catch(function () {
                        self.statusMsg = 'تعذّر تحميل الخريطة. تحقق من الاتصال بالإنترنت.';
                    });
                });
                if (window.hrScheduleLucide) {
                    window.hrScheduleLucide();
                }
                this.$nextTick(function () {
                    if (window.hrScheduleLucide) window.hrScheduleLucide();
                });
            },

            closeMap: function () {
                this.mapOpen = false;
                if (this.map) {
                    this.map.remove();
                    this.map = null;
                    this.marker = null;
                }
            },

            initMap: function () {
                if (!window.L || !this.$refs.mapBox) return;
                if (this.map) {
                    this.map.remove();
                    this.map = null;
                    this.marker = null;
                }
                var self = this;
                var startLat = this.hasCoords ? this.lat : DEFAULT_LAT;
                var startLng = this.hasCoords ? this.lng : DEFAULT_LNG;
                this.map = window.L.map(this.$refs.mapBox).setView([startLat, startLng], this.hasCoords ? 16 : 12);
                window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '&copy; OpenStreetMap',
                }).addTo(this.map);
                this.map.on('click', function (e) {
                    self.setMarker(e.latlng.lat, e.latlng.lng);
                });
                if (this.hasCoords) {
                    this.setMarker(this.lat, this.lng, false);
                }
                setTimeout(function () {
                    if (self.map) self.map.invalidateSize();
                }, 250);
            },

            setMarker: function (lat, lng, fetchAddr) {
                var self = this;
                if (fetchAddr === undefined) fetchAddr = true;
                this.lat = lat;
                this.lng = lng;
                this.hasCoords = true;
                this.syncHiddenCoords();
                if (!this.map || !window.L) return;
                if (this.marker) {
                    this.marker.setLatLng([lat, lng]);
                } else {
                    this.marker = window.L.marker([lat, lng], { draggable: true }).addTo(this.map);
                    this.marker.on('dragend', function () {
                        var p = self.marker.getLatLng();
                        self.setMarker(p.lat, p.lng);
                    });
                }
                if (fetchAddr) {
                    this.resolveAddress(lat, lng);
                }
            },

            useMyLocation: function () {
                this.fetchCurrentPosition(true);
            },

            fetchCurrentPosition: function (withMap) {
                var self = this;
                if (!navigator.geolocation) {
                    this.statusMsg = 'المتصفح لا يدعم تحديد الموقع.';
                    return;
                }
                this.geoLoading = true;
                this.statusMsg = 'جاري تحديد موقعك...';
                navigator.geolocation.getCurrentPosition(
                    function (pos) {
                        self.geoLoading = false;
                        self.statusMsg = '';
                        var lat = pos.coords.latitude;
                        var lng = pos.coords.longitude;
                        if (withMap && self.map) {
                            self.map.setView([lat, lng], 17);
                            self.setMarker(lat, lng);
                            return;
                        }
                        self.lat = lat;
                        self.lng = lng;
                        self.hasCoords = true;
                        self.syncHiddenCoords();
                        self.resolveAddress(lat, lng);
                    },
                    function () {
                        self.geoLoading = false;
                        self.statusMsg = 'تعذّر الوصول للموقع. اسمح بصلاحية الموقع أو حدّد يدوياً على الخريطة.';
                    },
                    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
                );
            },

            fetchMyLocationQuick: function () {
                this.fetchCurrentPosition(false);
            },

            confirmLocation: function () {
                var self = this;
                if (!this.inputEl) return;
                if (!this.hasCoords) {
                    this.statusMsg = 'حدّد موقعاً على الخريطة أو استخدم «موقعي الحالي».';
                    return;
                }
                var manual = (this.inputEl.value || '').trim();
                if (manual) {
                    this.address = manual;
                }
                if ((this.address || '').trim() && !this.loading) {
                    this.syncInputFromAddress();
                    this.syncHiddenCoords();
                    this.closeMap();
                    return;
                }
                this.resolveAddress(this.lat, this.lng).then(function () {
                    self.closeMap();
                });
            },
        };
    }

    function registerLocationPicker() {
        if (!window.Alpine || typeof window.Alpine.data !== 'function') return;
        window.Alpine.data('locationPicker', buildLocationPicker);
    }

    window.locationPicker = function () {
        return buildLocationPicker();
    };

    document.addEventListener('alpine:init', registerLocationPicker);
    registerLocationPicker();
})();
